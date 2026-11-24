"""Extração de campos para o score de conformidade (Goal 7), via Gemini com schema.

Fora do fan-in do lote. Falha do Gemini ou resposta inválida não trava nada: o campo fica ausente e vira
pendência no cálculo. O texto do documento é dado não confiável: só o que passa pela validação abaixo
(lista fixa de campos, formatos e enum) chega ao banco.

Quando a primeira página do documento possui camada de texto digital nativo (`pagina.texto_nativo = True`,
extraída diretamente pelo PyMuPDF sem OCR), a extração tenta primeiro enviar apenas o texto (`imagem_png=None`)
com o prompt específico `VERSAO_PROMPT_EXTRACAO_TEXTO`. Se faltar qualquer campo essencial esperado para aquele
tipo documental (ex.: dado presente apenas em carimbo ou figura dentro do PDF), faz fallback automático
enviando a imagem PNG da primeira página com o prompt `VERSAO_PROMPT_EXTRACAO`.
"""
import calendar
import logging
import re
from datetime import date, timedelta

import psycopg
import redis

from app import config, llm, prompts
from app.classificar import _imagem_primeira_pagina, montar_texto
from app.conformidade import parse_data, validar_cnpj, validar_cpf
from app.eventos import concluir_tarefa_pos, lote_cancelado, publicar_evento
from app.filas import enfileirar
from app.renomeacao import (
    atualizar_nome_padronizado,
    normalizar_competencia,
    normalizar_tipo_exame,
)

log = logging.getLogger(__name__)

TEXTO_MAX = 8000
VALOR_MAX = 200
DATAS = (
    "data_admissao",
    "data_exame",
    "data_termino",
    "data_emissao",
    "inicio_ferias",
    "fim_ferias",
    "inicio_periodo",
    "fim_periodo",
)


def _remover_pendencia_por_doc(documento_id: int, prefixo: str, r: redis.Redis | None = None) -> None:
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            row = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (documento_id,)).fetchone()
        if row is not None:
            concluir_tarefa_pos(row[0], f"{prefixo}:{documento_id}", r)
    except Exception:
        pass


def enfileirar_extracao(documento_id: int, r: redis.Redis | None = None, forcar: bool = False) -> bool:
    """Nunca levanta: falha ao enfileirar não pode derrubar a classificação nem a revisão.
    Se falhar, remove a pendência de extração do lote no Redis para não travar o acompanhamento."""
    try:
        cli = r or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        payload = {"documento_id": documento_id}
        if forcar:  # revisão humana: o handler ignora a marca de cancelamento do lote
            payload["forcar"] = True
        enfileirar(cli, config.FILA_EXTRAIR, payload)
        return True
    except Exception:
        log.warning("não foi possível enfileirar a extração do documento %s", documento_id)
        _remover_pendencia_por_doc(documento_id, "extracao", r)
        return False


def calcular_data_termino(inicio: date | None, numero, unidade) -> date | None:
    """Fim de contrato por prazo determinado. O dia do início conta: 45 dias a partir de 27/07/2024 terminam
    em 09/09/2024 (início + N - 1). Meses: mesmo dia N meses depois (limitado ao último dia do mês), menos 1 dia."""
    if inicio is None or isinstance(numero, bool) or not isinstance(numero, int) or not 0 < numero <= 3650:
        return None
    if unidade == "dias":
        return inicio + timedelta(days=numero - 1)
    if unidade == "meses":
        mes = inicio.month - 1 + numero
        ano, mes = inicio.year + mes // 12, mes % 12 + 1
        dia = min(inicio.day, calendar.monthrange(ano, mes)[1])
        return date(ano, mes, dia) - timedelta(days=1)
    return None


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
        elif campo == "competencia":
            comp = normalizar_competencia(v)
            if comp is None:
                continue
            v = comp
        saida[campo] = v
    if isinstance(dados.get("distingue_prestadora"), bool):
        saida["distingue_prestadora"] = "true" if dados["distingue_prestadora"] else "false"
    if dados.get("tipo_prazo") in prompts.TIPOS_PRAZO:
        saida["tipo_prazo"] = dados["tipo_prazo"]
    if "data_termino" not in saida and "data_admissao" in saida:  # data explícita prevalece; senão, calcula
        fim = calcular_data_termino(date.fromisoformat(saida["data_admissao"]), dados.get("prazo_numero"),
                                    dados.get("prazo_unidade"))
        if fim is not None:
            saida["data_termino"] = fim.isoformat()
    tipo_exame = normalizar_tipo_exame(dados.get("tipo_exame"))
    if tipo_exame is not None:
        saida["tipo_exame"] = tipo_exame
    return saida


def campos_essenciais_completos(tipo: str | None, campos: dict[str, str]) -> bool:
    """Verifica se a extração somente por texto preencheu todos os campos críticos e matematicamente
    válidos esperados para o tipo documental. Se faltar qualquer um, o fallback com imagem PNG é acionado."""
    if tipo == "atestado_medico":
        return bool(campos.get("nome") and campos.get("data_emissao"))

    if validar_cnpj(campos.get("cnpj_prestadora")) is None:
        return False

    if tipo == "folha_pagamento":
        return bool(campos.get("competencia"))

    if tipo == "folha_ponto":
        tem_periodo = bool(campos.get("competencia") or (campos.get("inicio_periodo") and campos.get("fim_periodo")))
        return bool(campos.get("nome") and tem_periodo)

    if not campos.get("nome") or validar_cpf(campos.get("cpf")) is None:
        return False

    if tipo == "aso":
        return bool(campos.get("data_exame") and campos.get("tipo_exame"))
    if tipo == "contrato_trabalho":
        prazo = campos.get("tipo_prazo")
        if not campos.get("data_admissao") or prazo not in ("determinado", "indeterminado"):
            return False
        if prazo == "determinado" and not campos.get("data_termino"):
            return False
        return True
    if tipo == "holerite":
        return bool(campos.get("competencia"))
    if tipo == "recibo_ferias":
        return bool(campos.get("inicio_ferias") and campos.get("fim_ferias"))
    return False


def _mesclar_campos_fallback(campos_texto: dict[str, str], campos_imagem: dict[str, str]) -> dict[str, str]:
    """Combina os campos da tentativa só-texto com os do fallback com imagem (que enxergou texto + imagem).
    A resposta com imagem prevalece, exceto se CNPJ/CPF dela vier inválido e o do texto nativo for válido."""
    mesclado = {**campos_texto, **campos_imagem}
    if validar_cnpj(campos_imagem.get("cnpj_prestadora")) is None and validar_cnpj(campos_texto.get("cnpj_prestadora")):
        mesclado["cnpj_prestadora"] = campos_texto["cnpj_prestadora"]
    if validar_cpf(campos_imagem.get("cpf")) is None and validar_cpf(campos_texto.get("cpf")):
        mesclado["cpf"] = campos_texto["cpf"]
    return mesclado


def _apurar_pendencias_lote(conn, lote_id: int) -> tuple[int, bool]:
    """Devolve (docs_pendentes_classificacao, ha_analise_ponto_pendente_no_lote)."""
    lote_row = conn.execute("SELECT docs_pendentes FROM lote WHERE id = %s", (lote_id,)).fetchone()
    docs_pendentes = lote_row[0] if lote_row else 0
    ap_pendente = (
        conn.execute(
            "SELECT 1 FROM documento d "
            "LEFT JOIN analise_ponto ap ON ap.documento_id = d.id "
            "WHERE d.lote_id = %s AND d.estado IN ('classificado', 'revisado') AND d.tipo = 'folha_ponto' "
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
    forcar = bool(payload.get("forcar"))  # revisão humana vale mesmo com o lote cancelado

    def cancelado(lote: int) -> bool:
        return not forcar and lote_cancelado(lote)

    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute("SELECT estado, lote_id, pagina_ini, tipo FROM documento WHERE id = %s", (doc_id,)).fetchone()
        if doc is None or doc[0] not in ("classificado", "revisado", "em_revisao"):
            return
        if cancelado(doc[1]):
            concluir_tarefa_pos(doc[1], f"extracao:{doc_id}")
            return
        paginas = conn.execute(
            "SELECT texto, texto_nativo FROM pagina WHERE documento_id = %s ORDER BY numero",
            (doc_id,),
        ).fetchall()
    lote_id, pagina_ini, tipo_doc = doc[1], doc[2], doc[3]
    texto_doc = montar_texto([t for t, _ in paginas], TEXTO_MAX)
    primeira_nativa = bool(paginas and paginas[0][1])

    log.info(
        "lote_%s | doc #%s (%s) -> extração iniciada em modo %s",
        lote_id, doc_id, tipo_doc, "nativo (só texto)" if primeira_nativa else "escaneado (texto + imagem)",
    )
    publicar_evento(
        lote_id,
        "extracao",
        f"Extraindo dados cadastrais (Gemini) do documento #{doc_id}...",
        documento_id=doc_id,
    )
    prompt_img = prompts.prompt_extracao(tipo_doc, texto_doc, com_imagem=True)
    prompt_texto = prompts.prompt_extracao(tipo_doc, texto_doc, com_imagem=False) if primeira_nativa else None
    try:
        if primeira_nativa:
            dados = llm.texto_gemini(llm.gemini_gerar(prompt_texto, prompts.SCHEMA_EXTRACAO, None))
        else:
            dados = llm.texto_gemini(
                llm.gemini_gerar(prompt_img, prompts.SCHEMA_EXTRACAO, _imagem_primeira_pagina(lote_id, pagina_ini))
            )
    except llm.LLMErro as e:
        log.warning("extração do documento %s indisponível: %s", doc_id, e)
        if cancelado(lote_id):
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
    if cancelado(lote_id):
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

    campos_limpos = limpar(dados)
    usou_imagem = not primeira_nativa
    if primeira_nativa and not campos_essenciais_completos(tipo_doc, campos_limpos):
        log.info(
            "lote_%s | doc #%s (%s) -> campos essenciais incompletos só com texto (%s); acionando fallback com imagem",
            lote_id, doc_id, tipo_doc, sorted(campos_limpos),
        )
        imagem_fallback = _imagem_primeira_pagina(lote_id, pagina_ini)
        if imagem_fallback is not None:
            try:
                dados_img = llm.texto_gemini(llm.gemini_gerar(prompt_img, prompts.SCHEMA_EXTRACAO, imagem_fallback))
                if isinstance(dados_img, dict):
                    campos_limpos = _mesclar_campos_fallback(campos_limpos, limpar(dados_img))
                    usou_imagem = True
            except llm.LLMErro as e:
                log.warning("fallback com imagem na extração do documento %s falhou: %s", doc_id, e)
    elif primeira_nativa:
        log.info(
            "lote_%s | doc #%s (%s) -> extração nativa só texto completa (%d campos, sem PNG)",
            lote_id, doc_id, tipo_doc, len(campos_limpos),
        )

    versao_usada = prompts.VERSAO_PROMPT_EXTRACAO if usou_imagem else prompts.VERSAO_PROMPT_EXTRACAO_TEXTO
    origem = f"gemini:{versao_usada}"
    with psycopg.connect(config.DATABASE_URL) as conn:  # substitui o que o Gemini gravou antes; correção humana fica
        if cancelado(lote_id):
            concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
            return
        conn.execute("DELETE FROM documento_campos WHERE documento_id = %s AND origem LIKE 'gemini:%%'", (doc_id,))
        for campo, valor in campos_limpos.items():
            conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, %s, %s, %s) "
                         "ON CONFLICT (documento_id, campo) DO NOTHING", (doc_id, campo, valor, origem))
        atualizar_nome_padronizado(conn, doc_id)
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
    forcar = bool(payload.get("forcar"))

    def cancelado(lote: int) -> bool:
        return not forcar and lote_cancelado(lote)

    lote_id = None
    docs_pend = 0
    ap_pend = False
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (doc_id,)).fetchone()
        if row is not None:
            lote_id = row[0]
            docs_pend, ap_pend = _apurar_pendencias_lote(conn, lote_id)
    if lote_id is not None and not cancelado(lote_id):
        etapa = _resolver_etapa_pos_extracao(lote_id, doc_id, docs_pend, ap_pend)
        publicar_evento(
            lote_id,
            etapa,
            f"Processamento concluído no documento #{doc_id}.",
            documento_id=doc_id,
        )
    elif lote_id is not None:
        concluir_tarefa_pos(lote_id, f"extracao:{doc_id}")
