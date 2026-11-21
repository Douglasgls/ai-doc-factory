"""GET /documentos, PATCH /documentos/{id}/tipo e DELETE /documentos/{id}, contra o Postgres do compose."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.routers.documentos import actions

client = TestClient(app)


@pytest.fixture
def banco(extracoes, monkeypatch, orgs):
    analises = []
    monkeypatch.setattr(actions, "enfileirar_analise", lambda doc_id, cliente=None: analises.append(doc_id))
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    lotes = []

    def lote(docs, estado="concluido", contrato_id=None):
        """docs: lista de (estado, tipo). Devolve (lote_id, [documento_id])."""
        lid = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes, contrato_id) "
            "VALUES (%s, 't.pdf', %s, 0, %s) RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex, estado, contrato_id)).fetchone()[0]
        lotes.append(lid)
        ids = []
        for n, (est, tipo) in enumerate(docs, start=1):
            i = conn.execute(
                "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
                "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", (lid, n, n, n, est, tipo)).fetchone()[0]
            conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, %s, %s, 'texto')",
                         (lid, n, i))
            ids.append(i)
        return lid, ids

    yield conn, lote, orgs.contrato, extracoes, analises
    conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (lotes,))
    conn.close()


def _ids(resp):
    return {g["tipo"]: [d["id"] for d in g["documentos"]] for g in resp.json()["grupos"]}


# ---------- GET /documentos ----------

def test_listar_por_contrato_agrupa_e_ordena(banco):
    _, lote, contrato, _, _ = banco
    c = contrato()
    l1, (a, b, desc, d) = lote([("classificado", "holerite"), ("classificado", "aso"),
                             ("em_revisao", "desconhecido"), ("segmentado", None)], contrato_id=c)
    l2, (x,) = lote([("classificado", "aso")], contrato_id=c)
    lote([("classificado", "aso")])  # lote sem contrato: não deve aparecer
    r = client.get("/documentos", params={"contrato_id": c})
    assert r.status_code == 200
    grupos = r.json()["grupos"]
    assert [g["tipo"] for g in grupos] == ["aso", "holerite", "desconhecido", "sem_tipo"]
    assert [g["total"] for g in grupos] == [2, 1, 1, 1]
    assert _ids(r) == {"aso": [b, x], "holerite": [a], "desconhecido": [desc], "sem_tipo": [d]}
    assert set(grupos[0]["documentos"][0]) >= {"id", "lote_id", "ordem", "pagina_ini", "pagina_fim", "estado",
                                               "tipo", "confianca", "contrato_id"}
    assert grupos[0]["documentos"][0]["contrato_id"] == c


def test_listar_sem_filtro_inclui_todos(banco):
    _, lote, contrato, _, _ = banco
    _, (a,) = lote([("erro", None)])
    _, (b,) = lote([("classificado", "aso")], contrato_id=contrato())
    r = client.get("/documentos")
    todos = {d["id"] for g in r.json()["grupos"] for d in g["documentos"]}
    assert {a, b} <= todos


def test_listar_ordem_dos_tipos_segue_config(banco):
    _, lote, contrato, _, _ = banco
    c = contrato()
    lote([("classificado", t) for t in reversed(config.TIPOS)], contrato_id=c)
    r = client.get("/documentos", params={"contrato_id": c})
    assert [g["tipo"] for g in r.json()["grupos"]] == list(config.TIPOS)


def test_listar_contrato_inexistente_404(banco):
    assert client.get("/documentos", params={"contrato_id": 999999999}).status_code == 404


def test_listar_falhou(banco):
    _, lote, contrato, _, _ = banco
    c = contrato()
    _, (ok, ruim) = lote([("classificado", "aso"), ("erro", None)], contrato_id=c)
    r = client.get("/documentos", params={"contrato_id": c, "falhou": "true"})
    assert _ids(r) == {"sem_tipo": [ruim]}
    r = client.get("/documentos", params={"contrato_id": c, "falhou": "false"})
    assert _ids(r) == {"aso": [ok]}
    r = client.get("/documentos", params={"contrato_id": c})
    assert _ids(r) == {"aso": [ok], "sem_tipo": [ruim]}


# ---------- PATCH ----------

def _patch(i, tipo="aso", revisor="ana"):
    return client.patch(f"/documentos/{i}/tipo", json={"tipo": tipo, "revisor": revisor})


def test_patch_feliz_preserva_tipo_original(banco):
    conn, lote, _, extracoes, _ = banco
    _, (i,) = lote([("classificado", "holerite")])
    r = _patch(i, "aso", "  ana ")
    assert r.status_code == 200
    j = r.json()
    assert (j["id"], j["estado"], j["tipo"], j["tipo_original"], j["revisor"]) == (i, "revisado", "aso", "holerite", "admin-falso@exemplo.invalid")
    assert j["revisado_em"] and j["paginas"][0]["numero"] == 1
    j = _patch(i, "contrato_trabalho", "impostor@exemplo.invalid").json()
    assert (j["tipo"], j["tipo_original"], j["revisor"]) == ("contrato_trabalho", "holerite", "admin-falso@exemplo.invalid")
    assert conn.execute("SELECT count(*) FROM documento WHERE revisor = 'impostor@exemplo.invalid'").fetchone()[0] == 0
    assert extracoes == [i, i]
    assert client.get(f"/documentos/{i}").json()["tipo"] == "contrato_trabalho"


def test_patch_validacoes(banco):
    _, lote, _, _, _ = banco
    _, (i,) = lote([("classificado", "aso")])
    assert _patch(i, "inexistente").status_code == 422
    assert _patch(i, "desconhecido").status_code == 422
    assert client.get(f"/documentos/{i}").json()["estado"] == "classificado"


def test_patch_404(banco):
    assert _patch(999999999).status_code == 404


@pytest.mark.parametrize("estado", ["segmentado", "erro"])
def test_patch_409(banco, estado):
    _, lote, _, extracoes, _ = banco
    _, (i,) = lote([(estado, None)])
    r = _patch(i)
    assert r.status_code == 409 and estado in r.json()["detail"]
    assert extracoes == []


def test_patch_aceita_em_revisao_e_revisado(banco):
    _, lote, _, _, _ = banco
    _, (a, b) = lote([("em_revisao", "desconhecido"), ("revisado", "aso")])
    assert _patch(a, "holerite").json()["tipo_original"] == "desconhecido"
    assert _patch(b, "holerite").status_code == 200


def test_patch_dispara_analise_so_ao_virar_folha_ponto(banco):
    _, lote, _, _, analises = banco
    _, (a, b, c) = lote([("classificado", "aso"), ("classificado", "folha_ponto"), ("classificado", "aso")])
    _patch(a, "folha_ponto")
    assert analises == [a]
    _patch(b, "folha_ponto")  # já era folha_ponto
    _patch(c, "holerite")
    assert analises == [a]


# ---------- DELETE ----------

def test_delete_204_cascata_e_paginas_preservadas(banco):
    conn, lote, _, _, _ = banco
    lid, (i, outro) = lote([("classificado", "folha_ponto"), ("classificado", "aso")])
    conn.execute("INSERT INTO analise_ponto (documento_id, estado) VALUES (%s, 'concluida')", (i,))
    conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, 'nome', 'x', 't')", (i,))
    antes = conn.execute("SELECT docs_pendentes FROM lote WHERE id = %s", (lid,)).fetchone()
    r = client.delete(f"/documentos/{i}")
    assert r.status_code == 204 and r.content == b""
    assert conn.execute("SELECT count(*) FROM documento WHERE id = %s", (i,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM analise_ponto WHERE documento_id = %s", (i,)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM documento_campos WHERE documento_id = %s", (i,)).fetchone()[0] == 0
    pag = conn.execute("SELECT documento_id, texto FROM pagina WHERE lote_id = %s AND numero = 1", (lid,)).fetchone()
    assert pag == (None, "texto")
    assert conn.execute("SELECT count(*) FROM documento WHERE id = %s", (outro,)).fetchone()[0] == 1
    assert conn.execute("SELECT docs_pendentes FROM lote WHERE id = %s", (lid,)).fetchone() == antes
    assert client.get(f"/documentos/{i}").status_code == 404


def test_delete_404(banco):
    assert client.delete("/documentos/999999999").status_code == 404


@pytest.mark.parametrize("estado", ["recebido", "ocr", "classificando"])
def test_delete_409_lote_em_andamento(banco, estado):
    _, lote, _, _, _ = banco
    _, (i,) = lote([("classificado", "aso")], estado=estado)
    assert client.delete(f"/documentos/{i}").status_code == 409
    assert client.get(f"/documentos/{i}").status_code == 200


def test_delete_lote_com_erro_permitido(banco):
    _, lote, _, _, _ = banco
    _, (i,) = lote([("erro", None)], estado="erro")
    assert client.delete(f"/documentos/{i}").status_code == 204
