"""GET /lotes: escopo por nível, cursor sem repetir nem pular, filtros e resumo. Contra o Postgres real; o cenário
cria dados próprios e apaga tudo no fim. O banco é compartilhado, então as asserções miram só os lotes do cenário."""
import time
import uuid

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from conftest import cnpj_valido

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)
INEXISTENTE = 2 ** 62


class Cen:
    pass


def _h(uid: int) -> dict:
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": str(uid), "iat": agora - 5, "exp": agora + 600}, config.AUTH_SEGREDO, algorithm="HS256")}


@pytest.fixture
def cen():
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    c = Cen()
    c.db = conn
    tom = {n: conn.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id",
                           (f"Tomador {n} {uuid.uuid4().hex}",)).fetchone()[0] for n in (1, 2)}
    pre = {n: conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING id",
                           (cnpj_valido(uuid.uuid4().int), f"Prestador {n} {uuid.uuid4().hex}")).fetchone()[0]
           for n in (1, 2)}
    pares = {"c11": (1, 1, True), "c12": (1, 2, True), "c21": (2, 1, True), "c22": (2, 2, False)}
    c.contrato = {n: conn.execute("INSERT INTO contrato (tomador_id, prestador_id, ativo) VALUES (%s, %s, %s) "
                                  "RETURNING id", (tom[t], pre[p], a)).fetchone()[0] for n, (t, p, a) in pares.items()}
    c.usuario = {}
    for nome in ("plat", "tom1", "prest1", "prest2"):
        nivel = "plataforma" if nome == "plat" else "tomador" if nome.startswith("tom") else "prestador"
        c.usuario[nome] = conn.execute(
            "INSERT INTO usuario (email, nome, nivel, papel, tomador_id, prestador_id) "
            "VALUES (%s, %s, %s, 'admin', %s, %s) RETURNING id",
            (f"{nome}-{uuid.uuid4().hex}@exemplo.invalid", nome, nivel,
             tom[1] if nivel == "tomador" else None, pre[int(nome[-1])] if nivel == "prestador" else None)
        ).fetchone()[0]
    c.lote = {}
    for rotulo, contrato in (("a1", "c11"), ("a2", "c11"), ("a3", "c11"), ("b1", "c12"), ("x1", "c21"),
                             ("i1", "c22"), ("s1", None)):
        c.lote[rotulo] = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, contrato_id) VALUES (%s, %s, 'concluido', %s) "
            "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex, f"{rotulo}.pdf", c.contrato.get(contrato))
        ).fetchone()[0]
    yield c
    conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (list(c.lote.values()),))
    conn.execute("DELETE FROM usuario WHERE id = ANY(%s)", (list(c.usuario.values()),))
    conn.execute("DELETE FROM contrato WHERE id = ANY(%s)", (list(c.contrato.values()),))
    conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (list(pre.values()),))
    conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (list(tom.values()),))
    conn.close()


def _ids(resp, cen):
    assert resp.status_code == 200, resp.text
    meus = set(cen.lote.values())
    return [i["id"] for i in resp.json()["itens"] if i["id"] in meus]


def _listar(cen, nome, **params):
    return client.get("/lotes", headers=_h(cen.usuario[nome]), params={"limite": 100, **params})


def test_prestador_nao_ve_lotes_de_outro_prestador(cen):
    l = cen.lote
    assert set(_ids(_listar(cen, "prest2"), cen)) == {l["b1"]}  # c22 inativo some; c11/c21 são do prestador 1
    assert set(_ids(_listar(cen, "prest1"), cen)) == {l["a1"], l["a2"], l["a3"], l["x1"]}


def test_tomador_ve_lotes_dos_seus_contratos_inclusive_inativo(cen):
    l = cen.lote
    cen.db.execute("UPDATE contrato SET ativo = false WHERE id = %s", (cen.contrato["c12"],))
    assert set(_ids(_listar(cen, "tom1"), cen)) == {l["a1"], l["a2"], l["a3"], l["b1"]}


def test_lote_sem_contrato_so_para_a_plataforma(cen):
    l = cen.lote
    for nome in ("tom1", "prest1", "prest2"):
        assert l["s1"] not in _ids(_listar(cen, nome), cen)
    assert set(_ids(_listar(cen, "plat"), cen)) == set(l.values())


def test_paginacao_por_cursor_sem_repetir_nem_pular(cen):
    esperado = sorted(cen.lote.values(), reverse=True)
    vistos, cursor = [], None
    for _ in range(500):
        params = {"limite": 2, **({"antes_de": cursor} if cursor else {})}
        corpo = client.get("/lotes", headers=_h(cen.usuario["plat"]), params=params).json()
        assert len(corpo["itens"]) <= 2
        vistos += [i["id"] for i in corpo["itens"]]
        cursor = corpo["proximo_cursor"]
        if cursor is None:
            break
    assert len(vistos) == len(set(vistos)), "lote repetido entre páginas"
    assert [i for i in vistos if i in set(cen.lote.values())] == esperado  # nenhum pulado, do mais novo ao mais antigo


def test_limite_invalido_da_422(cen):
    for limite in (0, 101):
        assert client.get("/lotes", headers=_h(cen.usuario["plat"]), params={"limite": limite}).status_code == 422


def test_filtros_estado_e_contrato(cen):
    l = cen.lote
    cen.db.execute("UPDATE lote SET estado = 'erro' WHERE id = ANY(%s)", ([l["a2"], l["b1"]],))
    assert set(_ids(_listar(cen, "tom1", estado="erro"), cen)) == {l["a2"], l["b1"]}
    assert set(_ids(_listar(cen, "prest1", estado="erro"), cen)) == {l["a2"]}
    assert set(_ids(_listar(cen, "tom1", contrato_id=cen.contrato["c11"]), cen)) == {l["a1"], l["a2"], l["a3"]}
    assert set(_ids(_listar(cen, "tom1", contrato_id=cen.contrato["c11"], estado="erro"), cen)) == {l["a2"]}


def test_contrato_fora_do_escopo_e_404_igual_ao_inexistente(cen):
    inexistente = _listar(cen, "prest2", contrato_id=INEXISTENTE)
    assert inexistente.status_code == 404
    for c in ("c11", "c21", "c22"):
        resp = _listar(cen, "prest2", contrato_id=cen.contrato[c])
        assert resp.status_code == 404 and resp.json() == inexistente.json()
    assert _listar(cen, "prest2", contrato_id=cen.contrato["c12"]).status_code == 200


def test_item_e_resumo_com_contagens(cen):
    lote = cen.lote["a1"]
    for ordem, estado in enumerate(("em_revisao", "em_revisao", "erro", "classificado"), 1):
        cen.db.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado) "
                       "VALUES (%s, %s, %s, %s, %s)", (lote, ordem, ordem, ordem, estado))
    itens = _listar(cen, "prest1").json()["itens"]
    item = next(i for i in itens if i["id"] == lote)
    assert item["total_documentos"] == 4 and item["em_revisao"] == 2 and item["com_erro"] == 1
    assert set(item) == {"id", "nome_arquivo", "estado", "docs_pendentes", "contrato_id", "criado_em",
                         "total_documentos", "em_revisao", "com_erro"}
    vazio = next(i for i in itens if i["id"] == cen.lote["a2"])
    assert vazio["total_documentos"] == 0 and vazio["em_revisao"] == 0 and vazio["com_erro"] == 0


def test_sem_token_da_401():
    assert client.get("/lotes").status_code == 401
