"""Classificador Jev (texto) + Gemini (segunda opinião com a imagem), mesma interface do classificador de regras.

A confiança é a do Jev. O Gemini só entra quando ela fica abaixo de CONF_AUTO, e só o TIPO dele é usado:
a confiança autodeclarada do Gemini não é pedida nem lida. Toda decisão de roteamento fica em roteamento.py.
"""
import logging

from app import config, llm, prompts
from app.anonimizacao import anonimizar_texto
from app.classificador_regras import Resultado

log = logging.getLogger(__name__)

STATUS_OK = "ok"
STATUS_INDISPONIVEL = "gemini_indisponivel"

_SCHEMA_GEMINI = {
    "type": "OBJECT",
    "properties": {"tipo": {"type": "STRING", "enum": list(config.TIPOS)}},
    "required": ["tipo"],
}


def _jev(texto: str) -> Resultado:
    questions = {"tipo": {"type": "choice", "instructions": prompts.INSTRUCOES_TIPO,
                          "criteria": prompts.DESCRICOES}}
    resp = llm.jev_decidir({"documento": {"texto": anonimizar_texto(texto)}}, questions)  # texto não confiável, em campo próprio
    try:
        resposta = resp["answers"]["tipo"]
        tipo = resposta["choice"]
        confianca = float(resposta["confidence"])
        brutas = resposta["probabilities"]
        modelo = resp["model"]
    except (KeyError, TypeError, ValueError) as e:
        raise llm.LLMErro("resposta do Jev fora do formato esperado") from e
    if tipo not in config.TIPOS and tipo != prompts.NENHUM:
        raise llm.LLMErro(f"Jev devolveu opção inválida: {tipo!r}")
    # por nome, nunca por posição; inclui a opção "nenhum" para ficar registrada
    probs = {t: float(brutas.get(t, 0.0)) for t in (*config.TIPOS, prompts.NENHUM)}
    if tipo == prompts.NENHUM:
        tipo = config.TIPO_DESCONHECIDO  # vai para revisão em decidir(), qualquer que seja a confiança
    return Resultado(tipo, confianca, probs, modelo, prompts.VERSAO_PROMPT)


def _segunda_opiniao(imagem: bytes | None) -> dict:
    """Só o tipo. Falha, imagem ausente ou tipo fora de TIPOS => status gemini_indisponivel (sem desacordo)."""
    info = {"modelo": config.GEMINI_MODEL, "versao_prompt": prompts.VERSAO_PROMPT_GEMINI, "tipo": None,
            "status": STATUS_INDISPONIVEL}
    if not imagem:
        return info
    try:
        resp = llm.gemini_gerar(prompts.prompt_gemini(), _SCHEMA_GEMINI, imagem)
        tipo = llm.texto_gemini(resp).get("tipo")
    except llm.LLMErro as e:
        log.warning("gemini indisponível: %s", e)
        return info
    info["modelo"] = resp.get("modelVersion") or config.GEMINI_MODEL  # o que a API realmente serviu
    if tipo in config.TIPOS:
        info.update(tipo=tipo, status=STATUS_OK)
    return info


def classificar(texto: str, imagem: bytes | None = None) -> Resultado:
    r = _jev(texto)
    if r.tipo == config.TIPO_DESCONHECIDO or r.confianca >= config.CONF_AUTO:
        return r  # "nenhum" já vai para revisão; confiança alta dispensa a segunda opinião
    seg = _segunda_opiniao(imagem)
    desacordo = seg["status"] == STATUS_OK and seg["tipo"] != r.tipo
    return r._replace(desacordo=desacordo, segunda_opiniao=seg)
