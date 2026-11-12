"""Análise de risco da folha de ponto (Goal 6): handler de analisar_folha_ponto.

Fluxo: Gemini extrai as marcações (texto do OCR + imagens + perfil) -> o código apura (app/ponto.py) e
compara com o Gemini (vale o código) -> o Jev julga uma situação por dimensão sobre contagens calculadas
pelo código -> score_geral em código. Apoio à auditoria, não parecer jurídico; convenção coletiva e acordo de
compensação podem alterar os limites do perfil padrão.

A análise fica fora do fan-in do lote e nunca altera documento.tipo nem documento.estado. As chamadas de
rede ficam fora das transações.
"""
import json
import logging
from pathlib import Path

import psycopg
import redis
from psycopg.types.json import Jsonb

from app import config, llm, ponto, prompts
from app.anonimizacao import anonimizar_texto
from app.eventos import lote_cancelado, publicar_evento

log = logging.getLogger(__name__)

_STR = {"type": "STRING"}
SCHEMA_GEMINI = {
    "type": "OBJECT",
    "properties": {
        "marcacoes": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "data": _STR,
            "pares": {"type": "ARRAY", "items": {"type": "ARRAY", "items": _STR}},
        }, "required": ["data", "pares"]}},
        "intervalo_pre_assinalado": {"type": "BOOLEAN"},
        "divergencias": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "tipo": {"type": "STRING", "enum": list(ponto.TIPOS_DIVERGENCIA)},
            "data": _STR, "minutos": {"type": "NUMBER"}, "base_legal": _STR, "evidencia": _STR,
        }, "required": ["tipo", "data", "minutos"]}},
        "analise": _STR,
        "horario_contratual": {"type": "ARRAY", "items": {"type": "ARRAY", "items": _STR}},
        "totais_declarados": {"type": "OBJECT", "properties": {
            "total_horas_min": {"type": "NUMBER", "nullable": True},
            "horas_extras_min": {"type": "NUMBER", "nullable": True},
        }},
    },
    "required": ["marcacoes", "intervalo_pre_assinalado", "divergencias", "analise", "horario_contratual",
                 "totais_declarados"],
}


def enfileirar_analise(documento_id: int, cliente: redis.Redis | None = None) -> None:
    """Nunca levanta: falha ao enfileirar não pode derrubar a classificação nem a revisão."""
    try:
        from app.filas import enfileirar
        cliente = cliente or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        enfileirar(cliente, config.FILA_ANALISAR, {"documento_id": documento_id})
    except Exception:
        log.exception("não foi possível enfileirar a análise de ponto do documento %s", documento_id)


def _validar_extracao(dado) -> dict:
    """Resposta do Gemini fora do formato vira LLMErro (a marcação em si, malformada, é tratada pelo código)."""
    if not isinstance(dado, dict) or not isinstance(dado.get("marcacoes"), list):
        raise llm.LLMErro("Gemini: 'marcacoes' ausente ou fora do formato")
    divs = dado.get("divergencias") or []
    if not isinstance(divs, list) or not all(isinstance(d, dict) for d in divs):
        raise llm.LLMErro("Gemini: 'divergencias' fora do formato")
    contrato = dado.get("horario_contratual")
    if not (isinstance(contrato, list) and all(isinstance(p, list) and len(p) == 2 for p in contrato)):
        contrato = []  # ausente ou fora do formato: só vale o teto diário (registrado em totais)
    decl = dado.get("totais_declarados") if isinstance(dado.get("totais_declarados"), dict) else {}
    declarados = {k: decl.get(k) if isinstance(decl.get(k), (int, float)) and not isinstance(decl.get(k), bool) else None
                  for k in ("total_horas_min", "horas_extras_min")}
    return {"marcacoes": dado["marcacoes"], "intervalo_pre_assinalado": dado.get("intervalo_pre_assinalado") is True,
            "divergencias": divs, "analise": str(dado.get("analise") or "")[:2000],
            "horario_contratual": contrato, "totais_declarados": declarados}


def extrair_com_gemini(texto: str, imagens: list[bytes], perfil: dict) -> tuple[dict, str, dict]:
    prompt = prompts.prompt_gemini_ponto(anonimizar_texto(texto[:config.PONTO_TEXTO_MAX]), json.dumps(perfil, ensure_ascii=False),
                                         ponto.TIPOS_DIVERGENCIA)
    resp = llm.gemini_gerar(prompt, SCHEMA_GEMINI, imagens=imagens, modelo=config.GEMINI_ANALISE_MODEL)
    dado = _validar_extracao(llm.texto_gemini(resp))
    return dado, resp.get("modelVersion") or config.GEMINI_ANALISE_MODEL, llm._uso(resp)


def julgar_com_jev(contagens: dict, analise: str) -> tuple[dict, str, dict]:
    """Uma única requisição, uma pergunta Score por dimensão. Devolve (respostas, modelo, usage)."""
    state = {"contagens": contagens, "analise_gemini": anonimizar_texto(analise)}  # texto não confiável em campo próprio
    resp = llm.jev_decidir(state, prompts.PERGUNTAS_PONTO)
    respostas = {}
    for dim, pergunta in prompts.PERGUNTAS_PONTO.items():
        try:
            r = resp["answers"][dim]
            respostas[dim] = {"score": float(r["score"]), "confianca": float(r["confidence"]),
                              "n_niveis": len(pergunta["criteria"]), "probabilidades": r["probabilities"]}
        except (KeyError, TypeError, ValueError) as e:
            raise llm.LLMErro(f"resposta do Jev sem a dimensão '{dim}' no formato esperado") from e
    return respostas, resp.get("model") or config.JEV_MODEL, llm._uso(resp)


def analisar(texto: str, imagens: list[bytes], perfil: dict) -> dict:
    """Pipeline completo (Gemini -> código -> Jev -> score). Levanta LLMErro em resposta inválida."""
    dado, modelo_gemini, uso_gemini = extrair_com_gemini(texto, imagens, perfil)
    apuracao = ponto.apurar_folha(dado["marcacoes"], perfil, intervalo_pre_assinalado=dado["intervalo_pre_assinalado"],
                                  horario_contratual=dado["horario_contratual"],
                                  totais_declarados=dado["totais_declarados"])
    britanico = ponto.detectar_ponto_britanico(dado["marcacoes"])
    comparacao = ponto.comparar_com_gemini(apuracao, dado["divergencias"])  # vale o código
    contagens = ponto.resumir_contagens(apuracao, britanico)
    respostas, modelo_jev, uso_jev = julgar_com_jev(contagens, dado["analise"])
    try:
        score = ponto.score_geral(respostas)
    except ValueError as e:
        raise llm.LLMErro(f"score do Jev inválido: {e}") from e
    return {
        "marcacoes": dado["marcacoes"], "intervalo_pre_assinalado": dado["intervalo_pre_assinalado"],
        "totais": {k: v for k, v in apuracao.items() if k != "divergencias"},
        "divergencias": comparacao["divergencias"], "diferencas_gemini": comparacao["diferencas"],
        "ponto_britanico": britanico, "analise": dado["analise"], "contagens": contagens,
        "scores_dimensao": {d: {**respostas[d], **score["dimensoes"][d]} for d in respostas},
        "score_geral": score["score_geral"], "requer_revisao": score["requer_revisao"],
        "modelo_gemini": modelo_gemini, "modelo_jev": modelo_jev,
        "custo": {"gemini": uso_gemini, "jev": uso_jev},
    }


def _imagens(lote_id: int, ini: int, fim: int) -> list[bytes]:
    saida = []
    for n in range(ini, min(fim, ini + config.PONTO_MAX_PAGINAS - 1) + 1):
        try:
            saida.append((Path(config.DATA_DIR) / f"lote_{lote_id}" / f"pag_{n:04d}.png").read_bytes())
        except OSError:
            log.warning("imagem da página %s do lote %s indisponível", n, lote_id)
    return saida


_UPSERT = """
INSERT INTO analise_ponto (documento_id, estado, erro, perfil, marcacoes, intervalo_pre_assinalado, totais,
    divergencias, diferencas_gemini, ponto_britanico, analise, contagens, scores_dimensao, score_geral,
    requer_revisao, modelo_gemini, modelo_jev, versao_prompt_gemini, versao_prompt_jev, custo, atualizado_em)
VALUES (%(documento_id)s, %(estado)s, %(erro)s, %(perfil)s, %(marcacoes)s, %(intervalo_pre_assinalado)s, %(totais)s,
    %(divergencias)s, %(diferencas_gemini)s, %(ponto_britanico)s, %(analise)s, %(contagens)s, %(scores_dimensao)s,
    %(score_geral)s, %(requer_revisao)s, %(modelo_gemini)s, %(modelo_jev)s, %(versao_prompt_gemini)s,
    %(versao_prompt_jev)s, %(custo)s, now())
ON CONFLICT (documento_id) DO UPDATE SET
    estado = EXCLUDED.estado, erro = EXCLUDED.erro, perfil = EXCLUDED.perfil, marcacoes = EXCLUDED.marcacoes,
    intervalo_pre_assinalado = EXCLUDED.intervalo_pre_assinalado, totais = EXCLUDED.totais,
    divergencias = EXCLUDED.divergencias, diferencas_gemini = EXCLUDED.diferencas_gemini,
    ponto_britanico = EXCLUDED.ponto_britanico, analise = EXCLUDED.analise, contagens = EXCLUDED.contagens,
    scores_dimensao = EXCLUDED.scores_dimensao, score_geral = EXCLUDED.score_geral,
    requer_revisao = EXCLUDED.requer_revisao, modelo_gemini = EXCLUDED.modelo_gemini, modelo_jev = EXCLUDED.modelo_jev,
    versao_prompt_gemini = EXCLUDED.versao_prompt_gemini, versao_prompt_jev = EXCLUDED.versao_prompt_jev,
    custo = EXCLUDED.custo, atualizado_em = now()
"""
_CAMPOS_JSON = ("perfil", "marcacoes", "totais", "divergencias", "diferencas_gemini", "ponto_britanico",
                "contagens", "scores_dimensao", "custo")


def _gravar(conn, documento_id: int, estado: str, dados: dict, erro: str | None = None) -> None:
    linha = {c: None for c in ("perfil", "marcacoes", "intervalo_pre_assinalado", "totais", "divergencias",
                               "diferencas_gemini", "ponto_britanico", "analise", "contagens", "scores_dimensao",
                               "score_geral", "modelo_gemini", "modelo_jev", "custo")}
    linha.update(dados)
    for c in _CAMPOS_JSON:
        if linha[c] is not None:
            linha[c] = Jsonb(linha[c])
    linha.update(documento_id=documento_id, estado=estado, erro=erro, requer_revisao=bool(dados.get("requer_revisao")),
                 versao_prompt_gemini=prompts.VERSAO_PROMPT_PONTO_GEMINI, versao_prompt_jev=prompts.VERSAO_PROMPT_PONTO_JEV)
    conn.execute(_UPSERT, linha)


def analisar_documento(payload: dict) -> None:
    doc_id = payload["documento_id"]
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = conn.execute("SELECT estado, tipo, lote_id, pagina_ini, pagina_fim FROM documento WHERE id = %s",
                           (doc_id,)).fetchone()
        if doc is None or doc[1] != "folha_ponto" or doc[0] not in ("classificado", "revisado"):
            return  # tipo mudou, documento removido ou ainda não decidido: nada a analisar
        if lote_cancelado(doc[2]):
            return
        textos = [t or "" for (t,) in conn.execute(
            "SELECT texto FROM pagina WHERE documento_id = %s ORDER BY numero", (doc_id,))]
        perfil = ponto.carregar_perfil(conn)
    publicar_evento(
        doc[2],
        "analise_ponto",
        f"Auditando folha de ponto #{doc_id} (Gemini + CLT + Jev)...",
        documento_id=doc_id,
    )
    resultado = analisar("\n".join(textos), _imagens(doc[2], doc[3], doc[4]), perfil)
    resultado["perfil"] = perfil
    with psycopg.connect(config.DATABASE_URL) as conn:
        _gravar(conn, doc_id, "concluida", resultado)  # uma linha por documento: reprocessar substitui
    publicar_evento(
        doc[2],
        "concluido",
        f"Auditoria da folha de ponto #{doc_id} concluída!",
        documento_id=doc_id,
    )


def marcar_erro_analise(payload: dict) -> None:
    """ao_esgotar: o job foi para a dlq. Grava a linha como erro (sem sobrescrever documento ou lote)."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        existe = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (payload["documento_id"],)).fetchone()
        if existe:
            _gravar(conn, payload["documento_id"], "erro", {}, erro="análise falhou após as tentativas; veja o log do worker_analise")
            publicar_evento(
                existe[0],
                "concluido",
                f"Auditoria da folha de ponto #{payload['documento_id']} finalizada com alerta.",
                documento_id=payload["documento_id"],
            )
