"""Jev, Gemini, cache e fronteiras com HTTP mockado (nenhum teste usa a rede)."""
import json
from pathlib import Path

import httpx
import pytest

from app import classificador_llm, config, llm, prompts, roteamento, segmentacao

PNG = b"\x89PNG fake"


def resp(status=200, corpo=None):
    return httpx.Response(status, json=corpo if corpo is not None else {})


def jev_ok(tipo="holerite", conf=0.95, modelo="jev-real-1"):
    probs = {t: 0.01 for t in (*config.TIPOS, prompts.NENHUM)}
    probs[tipo] = 0.94
    return {"model": modelo, "answers": {"tipo": {"type": "choice", "choice": tipo, "probabilities": probs,
                                                  "confidence": conf}},
            "usage": {"cost": 0.00001}, "id": "x", "provider": "p"}


def gemini_ok(tipo="aso", versao="gemini-3.6-flash"):
    return {"modelVersion": versao, "candidates": [{"content": {"parts": [{"text": json.dumps({"tipo": tipo})}]}}]}


@pytest.fixture
def rede(monkeypatch):
    """Cada lista é consumida em ordem (um item = uma chamada). Exceções são levantadas."""
    estado = {"jev": [], "gemini": [], "chamadas": [], "corpos": []}

    def enviar(url, headers, corpo):
        alvo = "jev" if "openrouter" in url else "gemini"
        estado["chamadas"].append(alvo)
        estado["corpos"].append(corpo)
        item = estado[alvo].pop(0)
        if isinstance(item, Exception):
            raise item
        return item
    monkeypatch.setattr(llm, "_enviar", enviar)
    monkeypatch.setattr(config, "CLASSIFICADOR", "jev")
    return estado


def test_jev_formato_e_probabilidades_por_nome(rede):
    rede["jev"].append(resp(corpo=jev_ok("recibo_ferias", 0.97)))
    r = classificador_llm.classificar("texto")
    assert (r.tipo, r.confianca, r.modelo, r.versao_prompt) == ("recibo_ferias", 0.97, "jev-real-1", prompts.VERSAO_PROMPT)
    assert set(r.probabilidades) == set(config.TIPOS) | {prompts.NENHUM} and r.probabilidades["recibo_ferias"] == 0.94
    assert r.segunda_opiniao is None and not r.desacordo
    corpo = rede["corpos"][0]
    assert corpo["state"] == {"documento": {"texto": "texto"}}  # texto não confiável em campo próprio
    q = corpo["questions"]["tipo"]
    assert q["type"] == "choice" and set(q["criteria"]) == set(config.TIPOS) | {prompts.NENHUM}
    assert "`documento.texto`" in q["instructions"]
    assert all(set(v) == {"what", "not_for", "examples"} for v in q["criteria"].values())
    assert prompts.NENHUM not in config.TIPOS


def test_nenhum_dos_anteriores_vai_para_revisao_desconhecido_sem_gemini(rede):
    rede["jev"].append(resp(corpo=jev_ok(prompts.NENHUM, 0.99)))
    r = classificador_llm.classificar("nota fiscal", PNG)
    assert r.tipo == config.TIPO_DESCONHECIDO and r.confianca == 0.99 and rede["chamadas"] == ["jev"]
    d = roteamento.decidir(r.confianca, r.tipo, r.desacordo)
    assert (d.estado, d.tipo, d.motivo) == ("em_revisao", "desconhecido", "nenhum_dos_anteriores")


def test_gemini_nao_e_chamado_com_confianca_alta(rede):
    rede["jev"].append(resp(corpo=jev_ok(conf=config.CONF_AUTO)))
    classificador_llm.classificar("t", PNG)
    assert rede["chamadas"] == ["jev"]


def test_acordo_e_desacordo(rede):
    rede["jev"] += [resp(corpo=jev_ok("aso", 0.6)), resp(corpo=jev_ok("aso", 0.6))]
    rede["gemini"] += [resp(corpo=gemini_ok("aso")), resp(corpo=gemini_ok("holerite"))]
    ok = classificador_llm.classificar("a", PNG)
    assert not ok.desacordo and ok.segunda_opiniao == {
        "modelo": "gemini-3.6-flash", "versao_prompt": prompts.VERSAO_PROMPT_GEMINI, "tipo": "aso", "status": "ok"}
    dif = classificador_llm.classificar("b", PNG + b"2")  # outra imagem: o cache do Gemini não responde
    assert dif.desacordo and dif.segunda_opiniao["tipo"] == "holerite"
    assert roteamento.decidir(dif.confianca, dif.tipo, dif.desacordo).motivo == "desacordo_modelos"


def test_confianca_autodeclarada_do_gemini_nao_e_pedida_nem_usada(rede):
    rede["jev"].append(resp(corpo=jev_ok("aso", 0.6)))
    g = gemini_ok("aso")
    g["candidates"][0]["content"]["parts"][0]["text"] = json.dumps({"tipo": "aso", "confianca": 0.01})
    rede["gemini"].append(resp(corpo=g))
    r = classificador_llm.classificar("a", PNG)
    schema = rede["corpos"][1]["generationConfig"]["responseSchema"]
    assert list(schema["properties"]) == ["tipo"]
    assert "confianc" not in json.dumps(r.segunda_opiniao) and r.confianca == 0.6 and not r.desacordo


@pytest.mark.parametrize("falha", ["rede", "5xx", "fora_de_tipos", "sem_imagem"])
def test_gemini_indisponivel_nao_vira_desacordo_nem_classificado(rede, falha):
    rede["jev"].append(resp(corpo=jev_ok("aso", 0.6)))
    if falha == "rede":
        rede["gemini"] += [httpx.ReadTimeout("x")] * config.LLM_TENTATIVAS
    elif falha == "5xx":
        rede["gemini"] += [resp(503)] * config.LLM_TENTATIVAS
    elif falha == "fora_de_tipos":
        rede["gemini"].append(resp(corpo=gemini_ok("outro")))
    r = classificador_llm.classificar("a", None if falha == "sem_imagem" else PNG)
    assert not r.desacordo and r.segunda_opiniao["status"] == "gemini_indisponivel"
    assert r.segunda_opiniao["tipo"] is None and r.confianca == 0.6
    assert roteamento.decidir(r.confianca, r.tipo, r.desacordo).estado == "em_revisao"


def test_retry_429_5xx_rede_e_depois_sucesso(rede):
    rede["jev"] += [resp(429), resp(503), httpx.ConnectError("x"), resp(corpo=jev_ok())]
    assert classificador_llm.classificar("t").tipo == "holerite"
    assert len(rede["chamadas"]) == 4


def test_401_nao_tenta_de_novo(rede):
    rede["jev"].append(resp(401))
    with pytest.raises(llm.LLMErro):
        classificador_llm.classificar("t")
    assert len(rede["chamadas"]) == 1


def test_jev_esgotado_levanta(rede):
    rede["jev"] += [resp(500)] * config.LLM_TENTATIVAS
    with pytest.raises(llm.LLMErro):
        classificador_llm.classificar("t")


def test_jev_opcao_invalida_levanta(rede):
    ruim = jev_ok()
    ruim["answers"]["tipo"]["choice"] = "xyz"
    rede["jev"].append(resp(corpo=ruim))
    with pytest.raises(llm.LLMErro):
        classificador_llm.classificar("t")


def test_cache_acerta_sem_nova_chamada_e_nao_contem_a_chave(rede, monkeypatch):
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "SEGREDO-OPENROUTER-XYZ")
    rede["jev"].append(resp(corpo=jev_ok()))
    a = classificador_llm.classificar("mesmo texto")
    b = classificador_llm.classificar("mesmo texto")  # fila vazia: se chamasse a rede, daria IndexError
    assert a == b and rede["chamadas"] == ["jev"]
    arquivos = list(Path(config.CACHE_DIR).glob("*.json"))
    assert len(arquivos) == 1
    conteudo = arquivos[0].read_text()
    assert "SEGREDO-OPENROUTER-XYZ" not in conteudo and "Bearer" not in conteudo
    rede["jev"].append(resp(corpo=jev_ok()))
    classificador_llm.classificar("outro texto")  # outra entrada: nova chamada
    assert len(rede["chamadas"]) == 2


def test_erro_nao_entra_no_cache(rede):
    rede["jev"] += [resp(401), resp(corpo={"sem": "answers"}), resp(corpo=jev_ok())]
    for _ in range(2):
        with pytest.raises(llm.LLMErro):
            classificador_llm.classificar("t")
    assert not list(Path(config.CACHE_DIR).glob("*.json"))
    assert classificador_llm.classificar("t").tipo == "holerite"  # a mesma entrada chama de novo
    assert len(rede["chamadas"]) == 3


def test_cache_do_gemini_separado_por_imagem(rede):
    rede["jev"] += [resp(corpo=jev_ok("aso", 0.6))] * 2
    rede["gemini"] += [resp(corpo=gemini_ok("aso")), resp(corpo=gemini_ok("aso"))]
    classificador_llm.classificar("t", PNG)
    classificador_llm.classificar("t", PNG + b"2")
    assert rede["chamadas"].count("gemini") == 2


# --- fronteiras (noul) ---

def noul(p):
    return resp(corpo={"model": "m", "answers": {"q": {"type": "noul", "noul": p}}, "usage": {}})


@pytest.mark.parametrize("p,esperado", [(0.95, True), (0.70, True), (0.05, False), (0.30, False), (0.50, None)])
def test_fronteira_limiares_em_codigo(rede, p, esperado):
    rede["jev"].append(noul(p))
    anterior = "CABECALHO " + "x" * 900 + " FIM"  # página longa: só o começo e o fim são enviados
    assert segmentacao.perguntar_llm_mesmo_documento(anterior, "inicio" + "y" * 900) is esperado
    corpo = rede["corpos"][0]
    assert corpo["questions"]["q"]["type"] == "noul"
    assert corpo["state"] == {
        "pagina_anterior": {"inicio": anterior[:config.SEG_LLM_CABECALHO], "fim": anterior[-config.SEG_LLM_TRECHO:]},
        "pagina_atual": {"inicio": ("inicio" + "y" * 900)[:config.SEG_LLM_TRECHO]}}
    instrucoes = corpo["questions"]["q"]["instructions"]
    assert all(c in instrucoes for c in ("`pagina_anterior.inicio`", "`pagina_anterior.fim`", "`pagina_atual.inicio`"))


def test_fronteira_em_modo_regras_nao_chama_a_rede(monkeypatch):
    monkeypatch.setattr(config, "CLASSIFICADOR", "regras")

    def proibido(*a, **k):
        pytest.fail("jev_sim_nao chamado com CLASSIFICADOR=regras")
    monkeypatch.setattr(llm, "jev_sim_nao", proibido)
    assert segmentacao.perguntar_llm_mesmo_documento("fim", "inicio") is None


def test_fronteira_falha_do_llm_devolve_none(rede):
    rede["jev"] += [resp(500)] * config.LLM_TENTATIVAS
    assert segmentacao.perguntar_llm_mesmo_documento("a", "b") is None
    rede["jev"].append(resp(corpo={"answers": {"q": {"noul": "talvez"}}}))
    assert segmentacao.perguntar_llm_mesmo_documento("a", "b") is None


def test_fronteira_usa_cache(rede):
    rede["jev"].append(noul(0.9))
    assert segmentacao.perguntar_llm_mesmo_documento("a", "b") is True
    assert segmentacao.perguntar_llm_mesmo_documento("a", "b") is True
    assert rede["chamadas"] == ["jev"]
