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
from app.eventos import lote_cancelado, publicar_evento
from app.filas import enfileirar

log = logging.getLogger(__name__)

TEXTO_MAX = 8000
VALOR_MAX = 200
DATAS = ("data_admissao", "data_exame", "data_termino")


def enfileirar_extracao(documento_id: int, r: redis.Redis | None = None) -> None:
    """Nunca levanta: falha ao enfileirar não pode derrubar a classificação nem a revisão."""
    try:
        r = r or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        enfileirar(r, config.FILA_EXTRAIR, {"documento_id": documento_id})
    except Exception:
        log.warning("não foi possível enfileirar a extração do documento %s", documento_id)


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


def extrair_campos(payload: dict) -> None:
    doc_id = payload["documento_id"]
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute("SELECT estado, lote_id, pagina_ini, tipo FROM documento WHERE id = %s", (doc_id,)).fetchone()
        if doc is None or doc[0] not in ("classificado", "revisado", "em_revisao"):
            return
        if lote_cancelado(doc[1]):
            return
        textos = [t for (t,) in conn.execute("SELECT texto FROM pagina WHERE documento_id = %s ORDER BY numero", (doc_id,))]
    publicar_evento(
        doc[1],
        "extracao",
        f"Extraindo dados cadastrais (Gemini) do documento #{doc_id}...",
        documento_id=doc_id,
    )
    prompt = prompts.prompt_extracao(doc[3], montar_texto(textos, TEXTO_MAX))
    try:
        dados = llm.texto_gemini(llm.gemini_gerar(prompt, prompts.SCHEMA_EXTRACAO, _imagem_primeira_pagina(doc[1], doc[2])))
    except llm.LLMErro as e:
        log.warning("extração do documento %s indisponível: %s", doc_id, e)
        publicar_evento(
            doc[1],
            "analise_ponto" if (doc[3] == "folha_ponto" and doc[0] == "classificado") else "concluido",
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
        return
    if not isinstance(dados, dict):
        log.warning("extração do documento %s: resposta fora do schema", doc_id)
        publicar_evento(
            doc[1],
            "analise_ponto" if (doc[3] == "folha_ponto" and doc[0] == "classificado") else "concluido",
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
        return
    origem = f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO}"
    campos_limpos = limpar(dados)
    espera_analise_ponto = False
    with psycopg.connect(config.DATABASE_URL) as conn:  # substitui o que o Gemini gravou antes; correção humana fica
        conn.execute("DELETE FROM documento_campos WHERE documento_id = %s AND origem LIKE 'gemini:%%'", (doc_id,))
        for campo, valor in campos_limpos.items():
            conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (documento_id, campo) DO NOTHING", (doc_id, campo, valor, origem))
        if doc[3] == "folha_ponto" and doc[0] == "classificado":
            ap = conn.execute("SELECT estado FROM analise_ponto WHERE documento_id = %s", (doc_id,)).fetchone()
            espera_analise_ponto = ap is None or ap[0] not in ("concluida", "erro")
    publicar_evento(
        doc[1],
        "analise_ponto" if espera_analise_ponto else "concluido",
        (
            f"Extração concluída ({len(campos_limpos)} campo(s)) · validando folha de ponto..."
            if espera_analise_ponto
            else f"Análise e validação concluídas ({len(campos_limpos)} campo(s) extraído(s))."
        ),
        documento_id=doc_id,
    )
