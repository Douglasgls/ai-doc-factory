"""Extração de campos para o score de conformidade (Goal 7), via Gemini com schema.

Fora do fan-in do lote. Falha do Gemini ou resposta inválida não trava nada: o campo fica ausente e vira
pendência no cálculo. O texto do documento é dado não confiável: só o que passa pela validação abaixo
(lista fixa de campos, formatos e enum) chega ao banco.
"""
import logging
import re

import psycopg
import redis

from app import config, llm, prompts
from app.classificar import _imagem_primeira_pagina, montar_texto
from app.conformidade import parse_data
from app.eventos import concluir_tarefa_pos, lote_cancelado, publicar_evento
from app.filas import enfileirar

log = logging.getLogger(__name__)

TEXTO_MAX = 8000
VALOR_MAX = 200
DATAS = ("data_admissao", "data_exame", "data_termino")


def _remover_pendencia_por_doc(documento_id: int, prefixo: str, r: redis.Redis | None = None) -> None:
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            row = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (documento_id,)).fetchone()
        if row is not None:
            concluir_tarefa_pos(row[0], f"{prefixo}:{documento_id}", r)
    except Exception:
        pass


def enfileirar_extracao(documento_id: int, r: redis.Redis | None = None) -> bool:
    """Nunca levanta: falha ao enfileirar não pode derrubar a classificação nem a revisão.
    Se falhar, remove a pendência de extração do lote no Redis para não travar o acompanhamento."""
    try:
        cli = r or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        enfileirar(cli, config.FILA_EXTRAIR, {"documento_id": documento_id})
        return True
    except Exception:
        log.warning("não foi possível enfileirar a extração do documento %s", documento_id)
        _remover_pendencia_por_doc(documento_id, "extracao", r)
        return False


def limpar(dados) -> dict[str, str]:
    """Aceita só os campos do schema, com formato válido; o resto é descartado."""
    if not isinstance(dados, dict):
        return {}
    saida: dict[str, str] = {}
    for campo in prompts.CAMPOS_EXTRACAO_TEXTO:
        v = dados.get(campo)
        if not isinstance(v, str):
            continue
        v = re.sub(r"\s+", " ", v).strip()
        if not v or len(v) > VALOR_MAX:
            continue
        if campo in DATAS:
            d = parse_data(v)
            if d is None:
                continue
            v = d.isoformat()
        saida[campo] = v
    if isinstance(dados.get("distingue_prestadora"), bool):
        saida["distingue_prestadora"] = "true" if dados["distingue_prestadora"] else "false"
    if dados.get("tipo_prazo") in prompts.TIPOS_PRAZO:
        saida["tipo_prazo"] = dados["tipo_prazo"]
    return saida


def _apurar_pendencias_lote(conn, lote_id: int) -> tuple[int, bool]:
    """Devolve (docs_pendentes_classificacao, ha_analise_ponto_pendente_no_lote)."""
    lote_row = conn.execute("SELECT docs_pendentes FROM lote WHERE id = %s", (lote_id,)).fetchone()
    docs_pendentes = lote_row[0] if lote_row else 0
    ap_pendente = (
        conn.execute(
            "SELECT 1 FROM documento d "
            "LEFT JOIN analise_ponto ap ON ap.documento_id = d.id "
            "WHERE d.lote_id = %s AND d.estado = 'classificado' AND d.tipo = 'folha_ponto' "
            "AND (ap.estado IS NULL OR ap.estado NOT IN ('concluida', 'erro')) "
            "LIMIT 1",
            (lote_id,),
        ).fetchone()
        is not None
    )
    return docs_pendentes, ap_pendente


def _resolver_etapa_pos_extracao(lote_id: int, doc_id: int, docs_pendentes: int, ap_pendente: bool) -> str:
    restantes_pos = concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
    if docs_pendentes > 0:
        return "classificando"
    if any(t.startswith("extracao:") for t in restantes_pos):
        return "extracao"
    if ap_pendente or any(t.startswith("analise:") for t in restantes_pos):
        return "analise_ponto"
    return "concluido"


def extrair_campos(payload: dict) -> None:
    doc_id = payload["documento_id"]
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute("SELECT estado, lote_id, pagina_ini, tipo FROM documento WHERE id = %s", (doc_id,)).fetchone()
        if doc is None or doc[0] not in ("classificado", "revisado", "em_revisao"):
            return
        if lote_cancelado(doc[1]):
            concluir_tarefa_pos(doc[1], f"extracao:{doc_id}")
            return
        textos = [t for (t,) in conn.execute("SELECT texto FROM pagina WHERE documento_id = %s ORDER BY numero", (doc_id,))]
    lote_id = doc[1]
    publicar_evento(
        lote_id,
        "extracao",
        f"Extraindo dados cadastrais (Gemini) do documento #{doc_id}...",
        documento_id=doc_id,
    )
    prompt = prompts.prompt_extracao(doc[3], montar_texto(textos, TEXTO_MAX))
    try:
        dados = llm.texto_gemini(llm.gemini_gerar(prompt, prompts.SCHEMA_EXTRACAO, _imagem_primeira_pagina(lote_id, doc[2])))
    except llm.LLMErro as e:
        log.warning("extração do documento %s indisponível: %s", doc_id, e)
        if lote_cancelado(lote_id):
            concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
            return
        with psycopg.connect(config.DATABASE_URL) as conn:
            docs_pend, ap_pend = _apurar_pendencias_lote(conn, lote_id)
        etapa = _resolver_etapa_pos_extracao(lote_id, doc_id, docs_pend, ap_pend)
        publicar_evento(
            lote_id,
            etapa,
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
        return
    if lote_cancelado(lote_id):
        concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
        return
    if not isinstance(dados, dict):
        log.warning("extração do documento %s: resposta fora do schema", doc_id)
        with psycopg.connect(config.DATABASE_URL) as conn:
            docs_pend, ap_pend = _apurar_pendencias_lote(conn, lote_id)
        etapa = _resolver_etapa_pos_extracao(lote_id, doc_id, docs_pend, ap_pend)
        publicar_evento(
            lote_id,
            etapa,
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
        return
    origem = f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO}"
    campos_limpos = limpar(dados)
    with psycopg.connect(config.DATABASE_URL) as conn:  # substitui o que o Gemini gravou antes; correção humana fica
        if lote_cancelado(lote_id):
            concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
            return
        conn.execute("DELETE FROM documento_campos WHERE documento_id = %s AND origem LIKE 'gemini:%%'", (doc_id,))
        for campo, valor in campos_limpos.items():
            conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (documento_id, campo) DO NOTHING", (doc_id, campo, valor, origem))
        docs_pend, ap_pend = _apurar_pendencias_lote(conn, lote_id)
    etapa = _resolver_etapa_pos_extracao(lote_id, doc_id, docs_pend, ap_pend)
    publicar_evento(
        lote_id,
        etapa,
        (
            f"Extração concluída ({len(campos_limpos)} campo(s)) · validando folha de ponto..."
            if etapa == "analise_ponto"
            else (
                f"Extração do documento #{doc_id} concluída ({len(campos_limpos)} campo(s))..."
                if etapa != "concluido"
                else f"Análise e validação concluídas ({len(campos_limpos)} campo(s) extraído(s))."
            )
        ),
        documento_id=doc_id,
    )


def marcar_erro_extracao(payload: dict) -> None:
    """ao_esgotar: job de extração foi para a dlq. Remove a pendência pós-classificação para não travar o lote."""
    doc_id = payload["documento_id"]
    lote_id = None
    docs_pend = 0
    ap_pend = False
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (doc_id,)).fetchone()
        if row is not None:
            lote_id = row[0]
            docs_pend, ap_pend = _apurar_pendencias_lote(conn, lote_id)
    if lote_id is not None and not lote_cancelado(lote_id):
        etapa = _resolver_etapa_pos_extracao(lote_id, doc_id, docs_pend, ap_pend)
        publicar_evento(
            lote_id,
            etapa,
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
    elif lote_id is not None:
        concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
