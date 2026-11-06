"""GET /tipos, campos extraídos nas respostas de documento, PUT /documentos/{id}/campos e GET /busca enriquecido."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app

client = TestClient(app)

ANTIGA = ("aso", "folha_pagamento", "folha_ponto", "holerite", "recibo_ferias", "atestado_medico",
          "contrato_trabalho")


@pytest.fixture
def banco():
    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    lotes = []

    def lote(estado_doc="em_revisao", tipo="aso", ini=2, fim=4, texto=None):
        lid = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) VALUES (%s, 'arq.pdf', 'concluido', 0) "
            "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        lotes.append(lid)
        did = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
            "VALUES (%s, 1, %s, %s, %s, %s) RETURNING id", (lid, ini, fim, estado_doc, tipo)).fetchone()[0]
        for n in range(ini, fim + 1):
            conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, %s, %s, %s)",
                         (lid, n, did, texto or "texto"))
        return lid, did

    yield conn, lote
    conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (lotes,))
    conn.close()


def _campo(conn, did, campo, valor, origem="modelo"):
    conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, %s, %s, %s)",
                 (did, campo, valor, origem))


def test_tipos():
    r = client.get("/tipos")
    assert r.status_code == 200
    corpo = r.json()
    assert [t["slug"] for t in corpo] == list(config.TIPOS_INFO)
    assert all(set(t) == {"slug", "nome", "icone"} for t in corpo)
    assert "desconhecido" not in [t["slug"] for t in corpo]
    assert corpo[0] == {"slug": "aso", "nome": "ASO (Atestado de Saúde Ocupacional)", "icone": "file"}
    assert config.TIPOS == ANTIGA
    assert config.TIPO_DESCONHECIDO == "desconhecido"


def test_campos_nas_tres_respostas(banco):
    conn, lote = banco
    lid, did = lote()
    _campo(conn, did, "nome", "Maria Silva")
    _campo(conn, did, "cpf", "52998224725")
    _, sem = lote(ini=1, fim=1)

    d = client.get(f"/documentos/{did}").json()
    assert d["campos"] == {"nome": "Maria Silva", "cpf": "***.982.247-**"}  # CPF sai mascarado
    assert d["pessoa"] == "Maria Silva"
    assert d["nome_arquivo"] == "arq.pdf"
    assert d["n_paginas"] == 3
    assert d["processado_em"]
    assert [p["numero"] for p in d["paginas"]] == [2, 3, 4]  # campos antigos preservados
    vazio = client.get(f"/documentos/{sem}").json()
    assert vazio["campos"] == {} and vazio["pessoa"] is None and vazio["n_paginas"] == 1

    itens = {i["id"]: i for g in client.get("/documentos").json()["grupos"] for i in g["documentos"]}
    assert itens[did]["campos"] == d["campos"] and itens[did]["pessoa"] == "Maria Silva"
    assert itens[did]["n_paginas"] == 3 and itens[did]["nome_arquivo"] == "arq.pdf"
    assert itens[sem]["pessoa"] is None

    fila = {i["id"]: i for i in client.get("/revisao").json()}
    assert fila[did]["campos"] == d["campos"] and fila[did]["pessoa"] == "Maria Silva"
    assert fila[did]["pagina_ini"] == 2 and fila[did]["pagina_fim"] == 4 and fila[did]["n_paginas"] == 3
    assert fila[did]["nome_arquivo"] == "arq.pdf" and fila[did]["processado_em"]
    assert fila[did]["tipo_sugerido"] == "aso" and fila[did]["imagem_url"] == f"/lotes/{lid}/paginas/2/imagem"


def test_put_campos_upsert_e_remocao(banco):
    conn, lote = banco
    _, did = lote(estado_doc="classificado")
    _campo(conn, did, "nome", "Antigo")
    _campo(conn, did, "cpf", "111")
    r = client.put(f"/documentos/{did}/campos",
                   json={"campos": {"nome": "Novo Nome", "matricula": "42", "cpf": None}, "revisor": " ana "})
    assert r.status_code == 200
    assert r.json()["campos"] == {"nome": "Novo Nome", "matricula": "42"}
    assert r.json()["pessoa"] == "Novo Nome"
    origens = dict(conn.execute("SELECT campo, origem FROM documento_campos WHERE documento_id = %s",
                                (did,)).fetchall())
    assert origens == {"nome": "humano", "matricula": "humano"}
    # remover campo inexistente é inofensivo
    assert client.put(f"/documentos/{did}/campos", json={"campos": {"xyz": None}, "revisor": "a"}).status_code == 200


@pytest.mark.parametrize("estado", ["segmentado", "erro", "revisado"])
def test_put_campos_qualquer_estado(banco, estado):
    _, lote = banco
    _, did = lote(estado_doc=estado)
    r = client.put(f"/documentos/{did}/campos", json={"campos": {"nome": "X"}, "revisor": "a"})
    assert r.status_code == 200 and r.json()["estado"] == estado


@pytest.mark.parametrize("corpo", [
    {"campos": {"Nome": "x"}, "revisor": "a"},
    {"campos": {"a-b": "x"}, "revisor": "a"},
    {"campos": {"a" * 41: "x"}, "revisor": "a"},
    {"campos": {"nome": "x" * 501}, "revisor": "a"},
    {"campos": {"nome": "  "}, "revisor": "a"},
    {"campos": {}, "revisor": "a"},
    {"campos": {"nome": "x"}, "revisor": "  "},
    {"campos": {"nome": "x"}},
])
def test_put_campos_validacao(banco, corpo):
    _, lote = banco
    _, did = lote()
    assert client.put(f"/documentos/{did}/campos", json=corpo).status_code == 422


def test_put_campos_limites_aceitos(banco):
    _, lote = banco
    _, did = lote()
    r = client.put(f"/documentos/{did}/campos", json={"campos": {"a" * 40: "x" * 500}, "revisor": "a"})
    assert r.status_code == 200


def test_put_campos_404():
    r = client.put("/documentos/999999999/campos", json={"campos": {"nome": "x"}, "revisor": "a"})
    assert r.status_code == 404


def test_busca_com_documento_tipo_arquivo_e_orfa(banco):
    conn, lote = banco
    palavra = "zzxqpalavra" + uuid.uuid4().hex[:6]
    lid, did = lote(tipo="holerite", ini=1, fim=1, texto=f"funcionario {palavra} admitido")
    conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 2, NULL, %s)",
                 (lid, f"orfa {palavra}"))
    r = client.get("/busca", params={"q": palavra})
    assert r.status_code == 200
    por_pagina = {x["pagina"]: x for x in r.json()}
    assert por_pagina[1]["documento_id"] == did and por_pagina[1]["tipo"] == "holerite"
    assert por_pagina[1]["nome_arquivo"] == "arq.pdf" and por_pagina[1]["lote_id"] == lid
    assert "<b>" in por_pagina[1]["trecho"]
    assert por_pagina[2]["documento_id"] is None and por_pagina[2]["tipo"] is None
    assert por_pagina[2]["nome_arquivo"] == "arq.pdf"
