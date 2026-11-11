"""Análise de folha de ponto (fila, Gemini, código, Jev, API) com HTTP mockado e Postgres/Redis do compose."""
import json
import uuid

import httpx
import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app import analise, classificar, config, llm, ocr, prompts
from app.api import app
from app.filas import DLQ, enfileirar, processar_um

client = TestClient(app)
IRREGULAR = [{"data": "2025-11-03", "pares": [["08:00", "12:00"], ["12:30", "20:30"]]},
             {"data": "2025-11-04", "pares": [["08:00", "12:00"], ["13:00", "17:00"]]}]
REGULAR = [{"data": "2025-11-03", "pares": [["08:00", "12:00"], ["13:00", "17:00"]]},
           {"data": "2025-11-04", "pares": [["08:00", "12:00"], ["13:00", "17:00"]]}]
GEM_OK_DIVS = [{"tipo": "horas_extras_acima_limite", "data": "2025-11-03", "minutos": 120},
               {"tipo": "intervalo_intrajornada_insuficiente", "data": "2025-11-03", "minutos": 30}]


def _gemini(marcacoes, divs=(), pre=False, versao="gemini-servido-9", **extra):
    texto = json.dumps({"marcacoes": marcacoes, "intervalo_pre_assinalado": pre, "divergencias": list(divs),
                        "analise": "Folha com horas extras.", **extra})
    return {"modelVersion": versao, "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
            "candidates": [{"content": {"parts": [{"text": texto}]}}]}


def _jev(corpo, scores, conf=0.9):
    """Responde só às dimensões que vieram nas perguntas. scores: {dimensao: nivel}."""
    answers = {}
    for dim, q in corpo["questions"].items():
        n = len(q["criteria"])
        answers[dim] = {"type": "score", "score": float(scores.get(dim, 0)), "confidence": conf.get(dim, 0.9)
                        if isinstance(conf, dict) else conf,
                        "legend": {}, "probabilities": {str(i): (1.0 if i == scores.get(dim, 0) else 0.0) for i in range(n)}}
    return {"model": "jev-servido-1", "answers": answers, "usage": {"cost": 0.00002}}


@pytest.fixture
def rede(monkeypatch, tmp_path):
    estado = {"gemini": [], "jev": [], "corpos": {"gemini": [], "jev": []}, "urls": []}

    def enviar(url, headers, corpo):
        alvo = "jev" if "openrouter" in url else "gemini"
        estado["corpos"][alvo].append(corpo)
        estado["urls"].append(url)
        item = estado[alvo].pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(corpo)
        return httpx.Response(200, json=item)
    monkeypatch.setattr(llm, "_enviar", enviar)
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(config, "GEMINI_ANALISE_MODEL", "gemini-analise-teste")
    return estado


def _doc(tipo="folha_ponto", estado="classificado", texto="CARTAO DE PONTO entrada saida", lote_pendentes=0):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) VALUES (%s, 't.pdf', 'classificando', %s) "
            "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex, lote_pendentes)).fetchone()[0]
        doc = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) VALUES (%s, 1, 1, 1, %s, %s) "
            "RETURNING id", (lote, estado, tipo)).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 1, %s, %s)",
                     (lote, doc, texto))
    return lote, doc


@pytest.fixture
def doc():
    lote, d = _doc()
    yield d
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def _linhas(doc_id):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute(
            "SELECT estado, divergencias, diferencas_gemini, scores_dimensao, score_geral, requer_revisao, "
            "modelo_gemini, modelo_jev, versao_prompt_gemini, versao_prompt_jev, contagens, erro, custo "
            "FROM analise_ponto WHERE documento_id = %s", (doc_id,)).fetchall()


def test_fluxo_completo_com_mock(doc, rede):
    rede["gemini"].append(_gemini(IRREGULAR, GEM_OK_DIVS))
    rede["jev"].append(lambda corpo: _jev(corpo, {"horas_extras": 2, "intervalos": 1}))
    analise.analisar_documento({"documento_id": doc})
    (linha,) = _linhas(doc)
    estado, divs, difs, scores, geral, revisao, mg, mj, vg, vj, contagens, erro, custo = linha
    assert estado == "concluida" and erro is None
    assert [(d["tipo"], d["data"], d["minutos"]) for d in divs] == [
        ("horas_extras_acima_limite", "2025-11-03", 120), ("intervalo_intrajornada_insuficiente", "2025-11-03", 30)]
    assert all(d["base_legal"] for d in divs) and difs == []
    assert set(scores) == set(prompts.DIMENSOES_PONTO) and scores["descanso"]["nao_avaliada"] is True  # 2 dias: sem semana completa
    assert scores["horas_extras"]["normalizado"] == pytest.approx(2 / 3)
    assert geral == pytest.approx(2 / 3) and not revisao  # máximo, não média
    assert (mg, mj) == ("gemini-servido-9", "jev-servido-1")  # modelo realmente servido
    assert (vg, vj) == (prompts.VERSAO_PROMPT_PONTO_GEMINI, prompts.VERSAO_PROMPT_PONTO_JEV)
    assert contagens["horas_extras"]["dias_acima_do_limite_diario"] == 1
    assert custo["jev"]["cost"] == 0.00002 and custo["gemini"]["promptTokenCount"] == 10
    # uma única requisição ao Jev, com state nomeado e contagens prontas
    assert len(rede["corpos"]["jev"]) == 1
    jev = rede["corpos"]["jev"][0]
    assert set(jev["state"]) == {"contagens", "analise_gemini"} and set(jev["questions"]) == set(prompts.DIMENSOES_PONTO) - {"descanso"}
    assert all(q["type"] == "score" for q in jev["questions"].values())
    assert "gemini-analise-teste" in rede["urls"][0]
    # o documento não muda
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT estado, tipo FROM documento WHERE id = %s", (doc,)).fetchone() == (
            "classificado", "folha_ponto")


def test_imagens_das_paginas_vao_ao_gemini(doc, rede, tmp_path):
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute("SELECT lote_id FROM documento WHERE id = %s", (doc,)).fetchone()[0]
    (tmp_path / f"lote_{lote}").mkdir()
    (tmp_path / f"lote_{lote}" / "pag_0001.png").write_bytes(b"\x89PNG fake")
    rede["gemini"].append(_gemini(REGULAR))
    rede["jev"].append(lambda corpo: _jev(corpo, {}))
    analise.analisar_documento({"documento_id": doc})
    partes = rede["corpos"]["gemini"][0]["contents"][0]["parts"]
    assert sum("inlineData" in p for p in partes) == 1
    assert "não confiável" in partes[0]["text"]  # o texto do OCR é tratado como não confiável


def test_gemini_com_contas_erradas_prevalece_o_codigo(doc, rede):
    errado = [{"tipo": "horas_extras_acima_limite", "data": "2025-11-03", "minutos": 90},
              {"tipo": "interjornada_insuficiente", "data": "2025-11-04", "minutos": 40}]
    rede["gemini"].append(_gemini(IRREGULAR, errado))
    rede["jev"].append(lambda corpo: _jev(corpo, {}))
    analise.analisar_documento({"documento_id": doc})
    (linha,) = _linhas(doc)
    assert [d["minutos"] for d in linha[1]] == [120, 30]  # vale o código
    assert {(d["tipo"], d["motivo"]) for d in linha[2]} == {
        ("horas_extras_acima_limite", "minutos_diferentes"),
        ("intervalo_intrajornada_insuficiente", "so_codigo"),
        ("interjornada_insuficiente", "so_gemini")}


def test_resposta_invalida_do_gemini_nao_grava_e_falha_definitiva_grava_erro(doc, rede):
    rede["gemini"].append({"modelVersion": "x", "candidates": [{"content": {"parts": [{"text": '{"foo": 1}'}]}}]})
    with pytest.raises(llm.LLMErro):
        analise.analisar_documento({"documento_id": doc})
    assert _linhas(doc) == []
    analise.marcar_erro_analise({"documento_id": doc})
    (linha,) = _linhas(doc)
    assert linha[0] == "erro" and linha[1] is None and linha[4] is None and linha[11]


def test_resposta_invalida_do_jev(doc, rede):
    rede["gemini"].append(_gemini(REGULAR))
    rede["jev"].append(lambda corpo: {"model": "j", "answers": {"horas_extras": {"type": "score"}}})
    with pytest.raises(llm.LLMErro):
        analise.analisar_documento({"documento_id": doc})
    assert _linhas(doc) == []


def test_dimensao_indeterminada_sinaliza_revisao_sem_mexer_no_documento(doc, rede):
    rede["gemini"].append(_gemini(IRREGULAR, GEM_OK_DIVS))
    rede["jev"].append(lambda corpo: _jev(corpo, {"horas_extras": 3, "intervalos": 1},
                                          conf={"horas_extras": 0.2, "intervalos": 0.9}))
    analise.analisar_documento({"documento_id": doc})
    (linha,) = _linhas(doc)
    assert linha[5] is True and linha[3]["horas_extras"]["indeterminada"] is True
    assert linha[4] == pytest.approx(1 / 3)  # a dimensão indeterminada não entra no máximo
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT estado, tipo FROM documento WHERE id = %s", (doc,)).fetchone() == (
            "classificado", "folha_ponto")


def test_reprocessar_substitui_sem_duplicar(doc, rede, monkeypatch, tmp_path):
    for marc, nivel in ((IRREGULAR, 3), (REGULAR, 0)):
        monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / f"cache{nivel}"))  # resposta nova, sem cache
        rede["gemini"].append(_gemini(marc, versao=f"v{nivel}"))
        rede["jev"].append(lambda corpo, n=nivel: _jev(corpo, {"horas_extras": n}))
        analise.analisar_documento({"documento_id": doc})
    (linha,) = _linhas(doc)
    assert linha[4] == 0.0 and linha[6] == "v0" and linha[1] == []


def test_documento_que_nao_e_folha_de_ponto_ou_nao_decidido_e_ignorado(rede):
    lote, d = _doc(tipo="holerite")
    lote2, d2 = _doc(estado="segmentado")
    analise.analisar_documento({"documento_id": d})
    analise.analisar_documento({"documento_id": d2})
    assert _linhas(d) == [] and _linhas(d2) == [] and rede["corpos"]["gemini"] == []
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id IN (%s, %s)", (lote, lote2))


@pytest.fixture
def fila_analise(monkeypatch):
    nome = f"teste_analise_{uuid.uuid4().hex[:8]}"
    monkeypatch.setattr(config, "FILA_ANALISAR", nome)
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    yield cli, nome
    cli.delete(nome, f"{nome}:proc")


def test_correcao_humana_para_folha_ponto_enfileira_a_analise(fila_analise):
    cli, fila = fila_analise
    lote, d = _doc(tipo="desconhecido", estado="em_revisao")
    resp = client.post(f"/documentos/{d}/revisao", json={"tipo": "folha_ponto", "revisor": "ana"})
    assert resp.status_code == 200 and cli.llen(fila) == 1
    assert json.loads(cli.lrange(fila, 0, 0)[0])["payload"] == {"documento_id": d}
    client.post(f"/documentos/{d}/revisao", json={"tipo": "holerite", "revisor": "ana"})
    assert cli.llen(fila) == 1  # outro tipo não enfileira
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_classificado_como_folha_ponto_enfileira_fora_do_fan_in(fila_analise):
    cli, fila = fila_analise
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote = conn.execute("INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 't.pdf', 'ocr') RETURNING id",
                            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, 1, %s)", (lote, "cartão de ponto "
                     "folha de ponto espelho de ponto entrada saída horas extras"))
    (d,) = ocr.segmentar_e_gravar(lote)
    classificar.classificar_documento({"documento_id": d})
    assert json.loads(cli.lrange(fila, 0, 0)[0])["payload"] == {"documento_id": d}
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT estado, tipo FROM documento WHERE id = %s", (d,)).fetchone() == (
            "classificado", "folha_ponto")
        assert conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (lote,)).fetchone() == ("concluido", 0)
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_falha_ao_enfileirar_nao_derruba_classificacao_nem_revisao(monkeypatch):
    class Quebrado:
        def lpush(self, *a):
            raise redis.ConnectionError("fora do ar")
    analise.enfileirar_analise(1, Quebrado())  # não levanta
    monkeypatch.setattr(redis.Redis, "from_url", staticmethod(lambda *a, **k: Quebrado()))
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote = conn.execute("INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 't.pdf', 'ocr') RETURNING id",
                            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, 1, %s)", (lote, "cartão de ponto "
                     "folha de ponto espelho de ponto entrada saída horas extras"))
    (d,) = ocr.segmentar_e_gravar(lote)
    classificar.classificar_documento({"documento_id": d})
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT estado FROM lote WHERE id = %s", (lote,)).fetchone()[0] == "concluido"
        conn.execute("UPDATE documento SET estado = 'em_revisao' WHERE id = %s", (d,))
    assert client.post(f"/documentos/{d}/revisao", json={"tipo": "folha_ponto", "revisor": "ana"}).status_code == 200
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_falha_da_analise_vai_para_dlq_e_grava_erro_sem_afetar_o_lote(doc, rede, fila_analise):
    cli, fila = fila_analise
    with psycopg.connect(config.DATABASE_URL) as conn:
        antes = conn.execute("SELECT l.estado, l.docs_pendentes FROM lote l JOIN documento d ON d.lote_id = l.id "
                             "WHERE d.id = %s", (doc,)).fetchone()
    enfileirar(cli, fila, {"documento_id": doc})
    for _ in range(config.MAX_TENTATIVAS):  # rede mockada sem respostas => IndexError em cada tentativa
        processar_um(cli, fila, analise.analisar_documento, timeout=1, ao_esgotar=analise.marcar_erro_analise)
    (linha,) = _linhas(doc)
    assert linha[0] == "erro"
    mortos = [x for x in cli.lrange(DLQ, 0, -1) if json.loads(x)["fila"] == fila]
    assert len(mortos) == 1
    for x in mortos:
        cli.lrem(DLQ, 0, x)
    with psycopg.connect(config.DATABASE_URL) as conn:
        depois = conn.execute("SELECT l.estado, l.docs_pendentes FROM lote l JOIN documento d ON d.lote_id = l.id "
                              "WHERE d.id = %s", (doc,)).fetchone()
    assert antes == depois


def test_endpoint_devolve_a_analise_pendente_e_concluida(doc, rede):
    assert client.get(f"/documentos/{doc}/analise-ponto").json() == {"documento_id": doc, "estado": "pendente"}
    rede["gemini"].append(_gemini(IRREGULAR, GEM_OK_DIVS))
    rede["jev"].append(lambda corpo: _jev(corpo, {"horas_extras": 2}))
    analise.analisar_documento({"documento_id": doc})
    corpo = client.get(f"/documentos/{doc}/analise-ponto").json()
    assert corpo["estado"] == "concluida" and corpo["score_geral"] == pytest.approx(2 / 3)
    assert corpo["divergencias"][0]["base_legal"] and corpo["perfil"]["extras_max_dia_min"]["valor"] == 120
    assert client.get("/documentos/99999999/analise-ponto").status_code == 404
    lote, holerite = _doc(tipo="holerite")
    assert client.get(f"/documentos/{holerite}/analise-ponto").status_code == 404
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_folha_irregular_pontua_acima_da_regular(rede, monkeypatch, tmp_path):
    resultados = []
    for marc, divs, niveis in ((IRREGULAR, GEM_OK_DIVS, {"horas_extras": 3, "intervalos": 2}), (REGULAR, [], {})):
        monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / f"c{len(resultados)}"))
        lote, d = _doc()
        rede["gemini"].append(_gemini(marc, divs))
        rede["jev"].append(lambda corpo, n=niveis: _jev(corpo, n))
        analise.analisar_documento({"documento_id": d})
        resultados.append(_linhas(d)[0][4])
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))
    assert resultados[0] > resultados[1]


def test_horario_contratual_e_totais_declarados_extraidos_viram_calculo_e_divergencia(doc, rede):
    rede["gemini"].append(_gemini(
        IRREGULAR, GEM_OK_DIVS, horario_contratual=[["08:00", "12:00"], ["13:00", "17:00"]],
        totais_declarados={"total_horas_min": 1200, "horas_extras_min": 180}))  # bruto recalculado: 240
    rede["jev"].append(lambda corpo: _jev(corpo, {"registro": 2}))
    analise.analisar_documento({"documento_id": doc})
    corpo = client.get(f"/documentos/{doc}/analise-ponto").json()
    totais_div = [d for d in corpo["divergencias"] if d["tipo"] == "total_declarado_divergente"]
    assert [(d["campo"], d["minutos"]) for d in totais_div] == [("horas_extras", 60)]  # total de horas bate (1200)
    assert corpo["totais"]["declarados"]["extras_bruto_min"] == 240
    assert corpo["totais"]["tolerancia_por_marcacao"]["aplicada"] is True
    assert corpo["contagens"]["registro"]["totais_declarados_divergentes"] == 1
    assert rede["corpos"]["jev"][0]["state"]["contagens"]["registro"]["maior_diferenca_do_total_declarado_min"] == 60
    props = rede["corpos"]["gemini"][0]["generationConfig"]["responseSchema"]["properties"]
    assert {"horario_contratual", "totais_declarados"} <= set(props)


def test_extracao_sem_horario_nem_totais_segue_so_com_o_teto_diario(doc, rede):
    rede["gemini"].append(_gemini(REGULAR, horario_contratual="lixo", totais_declarados={"horas_extras_min": None}))
    rede["jev"].append(lambda corpo: _jev(corpo, {}))
    analise.analisar_documento({"documento_id": doc})
    t = client.get(f"/documentos/{doc}/analise-ponto").json()["totais"]
    assert t["tolerancia_por_marcacao"]["aplicada"] is False and t["declarados"]["comparado"] is False
