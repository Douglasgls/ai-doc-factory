"""Classificação + roteamento + fan-in + API de revisão, contra o Postgres do compose."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.classificar import classificar_documento, montar_texto

FACIL = "HOLERITE proventos descontos líquido a receber"
SEM_PALAVRA = "lorem ipsum dolor sit amet"
client = TestClient(app)


def _criar_lote(docs):
    """docs: lista de (texto, segmentacao_ambigua). Devolve (lote_id, [documento_id])."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) VALUES (%s, 't.pdf', 'classificando', %s) "
            "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex, len(docs))).fetchone()[0]
        ids = []
        for n, (texto, amb) in enumerate(docs, start=1):
            i = conn.execute(
                "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, segmentacao_ambigua) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id", (lote, n, n, n, amb)).fetchone()[0]
            conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, %s, %s, %s)",
                         (lote, n, i, texto))
            ids.append(i)
    return lote, ids


@pytest.fixture
def criar():
    lotes = []

    def _f(docs):
        lote, ids = _criar_lote(docs)
        lotes.append(lote)
        return lote, ids
    yield _f
    with psycopg.connect(config.DATABASE_URL) as conn:
        for l in lotes:
            conn.execute("DELETE FROM lote WHERE id = %s", (l,))


def _doc(id_):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute(
            "SELECT estado, tipo, confianca, modelo, versao_prompt, probabilidades, motivo_revisao, tipo_original "
            "FROM documento WHERE id = %s", (id_,)).fetchone()


def _lote(id_):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (id_,)).fetchone()


def test_montar_texto_trunca():
    assert len(montar_texto(["a" * 5000, "b" * 5000])) == 6000
    assert montar_texto([None, "x"]) == "\nx"


def test_fan_in_com_classificado_e_em_revisao(criar):
    lote, (a, b, c) = criar([(FACIL, False), (SEM_PALAVRA, False), (FACIL, True)])
    for i in (a, b, c):
        classificar_documento({"documento_id": i})
    estado, tipo, conf, modelo, versao, probs, motivo, original = _doc(a)
    assert (estado, tipo, modelo, versao, motivo, original) == ("classificado", "holerite", "regras-v0", None, None, None)
    assert conf == 1.0 and probs["holerite"] == 1.0
    estado, tipo, conf, *_, motivo, _o = _doc(b)
    assert (estado, tipo, conf) == ("em_revisao", config.TIPO_DESCONHECIDO, 0.0) and motivo == "confianca_baixa"
    estado, tipo, *_, motivo, _o = _doc(c)  # segmentação ambígua preserva o tipo sugerido
    assert (estado, tipo, motivo) == ("em_revisao", "holerite", "segmentacao_ambigua")
    assert _lote(lote) == ("concluido", 0)


def test_job_repetido_nao_decrementa_nem_sobrescreve_revisado(criar):
    lote, (a, b) = criar([(SEM_PALAVRA, False), (FACIL, False)])
    classificar_documento({"documento_id": a})
    classificar_documento({"documento_id": a})  # repetido sobre em_revisao
    assert _lote(lote) == ("classificando", 1)
    r = client.post(f"/documentos/{a}/revisao", json={"tipo": "aso", "revisor": "ana"})
    assert r.status_code == 200
    classificar_documento({"documento_id": a})  # repetido sobre revisado
    estado, tipo, *_ = _doc(a)
    assert (estado, tipo) == ("revisado", "aso") and _lote(lote) == ("classificando", 1)
    classificar_documento({"documento_id": b})
    assert _lote(lote) == ("concluido", 0)


def test_revisao_preserva_tipo_original_e_aceita_confirmacao(criar):
    _, (a, b) = criar([(SEM_PALAVRA, False), ("HOLERITE proventos", False)])
    for i in (a, b):
        classificar_documento({"documento_id": i})
    r1 = client.post(f"/documentos/{a}/revisao", json={"tipo": "aso", "revisor": " ana "}).json()
    assert (r1["estado"], r1["tipo"], r1["tipo_original"], r1["revisor"]) == (
        "revisado", "aso", config.TIPO_DESCONHECIDO, "admin-falso@exemplo.invalid") and r1["revisado_em"]
    r2 = client.post(f"/documentos/{a}/revisao", json={"tipo": "holerite", "revisor": "bia"}).json()
    assert (r2["tipo"], r2["tipo_original"], r2["revisor"]) == ("holerite", config.TIPO_DESCONHECIDO, "admin-falso@exemplo.invalid")
    r3 = client.post(f"/documentos/{b}/revisao", json={"tipo": "holerite", "revisor": "ana"}).json()
    assert (r3["estado"], r3["tipo"], r3["tipo_original"]) == ("revisado", "holerite", "holerite")  # confirmou
    d = client.get(f"/documentos/{a}").json()
    assert d["tipo_original"] == config.TIPO_DESCONHECIDO and d["revisor"] == "admin-falso@exemplo.invalid" and d["revisado_em"]
    assert d["motivo_revisao"] == "confianca_baixa" and set(d["probabilidades"]) == set(config.TIPOS)


def test_revisao_ignora_revisor_do_corpo(criar):
    _, (a,) = criar([(SEM_PALAVRA, False)])
    classificar_documento({"documento_id": a})
    r = client.post(f"/documentos/{a}/revisao", json={"tipo": "aso", "revisor": "impostor@exemplo.invalid"})
    assert r.status_code == 200 and r.json()["revisor"] == "admin-falso@exemplo.invalid"
    assert client.get(f"/documentos/{a}").json()["revisor"] == "admin-falso@exemplo.invalid"
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT revisor FROM documento WHERE id = %s", (a,)).fetchone()[0] == "admin-falso@exemplo.invalid"
        assert conn.execute("SELECT count(*) FROM documento WHERE revisor = 'impostor@exemplo.invalid'").fetchone()[0] == 0
    # sem revisor no corpo também funciona
    r = client.post(f"/documentos/{a}/revisao", json={"tipo": "holerite"})
    assert r.status_code == 200 and r.json()["revisor"] == "admin-falso@exemplo.invalid"


def test_revisao_erros(criar):
    _, (seg, cls, rev) = criar([(SEM_PALAVRA, False), (FACIL, False), (SEM_PALAVRA, False)])
    classificar_documento({"documento_id": cls})  # classificado
    ok = {"tipo": "aso", "revisor": "ana"}
    assert client.post("/documentos/999999999/revisao", json=ok).status_code == 404
    assert client.post(f"/documentos/{seg}/revisao", json=ok).status_code == 409  # segmentado
    assert client.post(f"/documentos/{cls}/revisao", json=ok).status_code == 409  # classificado
    classificar_documento({"documento_id": rev})
    assert client.post(f"/documentos/{rev}/revisao", json={"tipo": "xyz", "revisor": "ana"}).status_code == 422
    assert client.post(f"/documentos/{rev}/revisao",
                       json={"tipo": config.TIPO_DESCONHECIDO, "revisor": "ana"}).status_code == 422
    assert client.post(f"/documentos/{rev}/revisao", json={}).status_code == 422  # tipo é obrigatório
    assert _doc(rev)[0] == "em_revisao"  # nada mudou


def test_fila_de_revisao(criar):
    lote, (a, b, c) = criar([(SEM_PALAVRA, False), (FACIL, False), ("HOLERITE proventos", False)])
    for i in (a, b, c):
        classificar_documento({"documento_id": i})
    fila = [x for x in client.get("/revisao").json() if x["lote_id"] == lote]
    assert [x["id"] for x in fila] == [a, c]  # estável: por lote e ordem; o classificado não aparece
    assert fila[0]["tipo_sugerido"] == config.TIPO_DESCONHECIDO and fila[0]["motivo"] == "confianca_baixa"
    assert fila[0]["imagem_url"] == f"/lotes/{lote}/paginas/1/imagem" and fila[1]["confianca"] < config.CONF_AUTO
    client.post(f"/documentos/{a}/revisao", json={"tipo": "aso", "revisor": "ana"})
    assert [x["id"] for x in client.get("/revisao").json() if x["lote_id"] == lote] == [c]
