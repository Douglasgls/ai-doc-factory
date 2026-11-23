"""POST/GET /tomadores, /prestadores e /contratos (só a plataforma), contra o Postgres. Cada teste apaga o que criou.
O 403 para tomador e prestador (usuários) é coberto pela varredura de tests/test_autenticacao.py."""
import uuid

import psycopg
import pytest
from conftest import cnpj_valido
from fastapi.testclient import TestClient

from app import config
from app.api import app

client = TestClient(app)


def _cnpj() -> str:
    return cnpj_valido(uuid.uuid4().int)


def _pontuado(c: str) -> str:
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def _nome() -> str:
    return f"Org {uuid.uuid4().hex}"


@pytest.fixture
def criar(orgs):
    """Cria pela API e registra para a limpeza."""
    def tomador(**corpo):
        r = client.post("/tomadores", json={"nome": _nome(), **corpo})
        if r.status_code == 201:
            orgs.registrar("tomador", r.json()["id"])
        return r

    def prestador(**corpo):
        r = client.post("/prestadores", json={"cnpj": _cnpj(), "razao_social": _nome(), **corpo})
        if r.status_code == 201:
            orgs.registrar("prestador", r.json()["id"])
        return r

    def contrato(tomador_id, prestador_id, **corpo):
        r = client.post("/contratos", json={"tomador_id": tomador_id, "prestador_id": prestador_id, **corpo})
        if r.status_code == 201:
            orgs.registrar("contrato", r.json()["id"])
        return r

    return tomador, prestador, contrato


# ---------- tomadores ----------

def test_tomador_cria_e_lista(criar):
    tomador, _, _ = criar
    nome = _nome()
    r = tomador(nome=f"  {nome}  ")
    assert r.status_code == 201
    corpo = r.json()
    assert set(corpo) == {"id", "nome", "cnpj", "ativo", "criado_em"}
    assert corpo["nome"] == nome and corpo["cnpj"] is None and corpo["ativo"] is True
    assert corpo["id"] in {t["id"] for t in client.get("/tomadores").json()}


@pytest.mark.parametrize("pontuacao", [False, True])
def test_tomador_cnpj_com_e_sem_pontuacao(criar, pontuacao):
    tomador, _, _ = criar
    cnpj = _cnpj()
    r = tomador(cnpj=_pontuado(cnpj) if pontuacao else cnpj)
    assert r.status_code == 201 and r.json()["cnpj"] == cnpj


@pytest.mark.parametrize("cnpj", ["", "   ", None])
def test_tomador_cnpj_vazio_vira_nulo(criar, cnpj):
    tomador, _, _ = criar
    r = tomador(cnpj=cnpj)
    assert r.status_code == 201 and r.json()["cnpj"] is None


def test_tomador_cnpj_invalido_422(criar):
    tomador, _, _ = criar
    for cnpj in ("11222333000180", "123", "00000000000000", "abc11222333000181"):
        r = tomador(cnpj=cnpj)
        assert r.status_code == 422, cnpj
        assert "CNPJ" in r.text


def test_tomador_nome_vazio_422(criar):
    tomador, _, _ = criar
    assert tomador(nome="   ").status_code == 422
    assert client.post("/tomadores", json={}).status_code == 422


def test_tomador_nome_repetido_409_sem_diferenciar_caixa(criar):
    tomador, _, _ = criar
    nome = _nome()
    primeiro = tomador(nome=nome)
    assert primeiro.status_code == 201
    r = tomador(nome=f"  {nome.upper()} ")
    assert r.status_code == 409
    assert str(primeiro.json()["id"]) in r.json()["detail"] and "nome" in r.json()["detail"]


def test_tomador_cnpj_repetido_409(criar):
    tomador, _, _ = criar
    cnpj = _cnpj()
    primeiro = tomador(cnpj=cnpj)
    r = tomador(cnpj=_pontuado(cnpj))  # mesma empresa, outra grafia e outro nome
    assert r.status_code == 409
    assert cnpj in r.json()["detail"] and str(primeiro.json()["id"]) in r.json()["detail"]


# ---------- prestadores ----------

def test_prestador_cria_e_lista(criar):
    _, prestador, _ = criar
    cnpj, razao = _cnpj(), _nome()
    r = prestador(cnpj=_pontuado(cnpj), razao_social=f"  {razao} ")
    assert r.status_code == 201
    corpo = r.json()
    assert set(corpo) == {"id", "cnpj", "razao_social", "ativo", "criado_em"}
    assert corpo["cnpj"] == cnpj and corpo["razao_social"] == razao and corpo["ativo"] is True
    assert corpo["id"] in {p["id"] for p in client.get("/prestadores").json()}


def test_prestador_cnpj_invalido_e_obrigatorio_422(criar):
    _, prestador, _ = criar
    assert prestador(cnpj="11222333000180").status_code == 422
    assert prestador(cnpj="12.345.678/0001-96").status_code == 422
    assert client.post("/prestadores", json={"razao_social": "X"}).status_code == 422
    assert prestador(razao_social=" ").status_code == 422


def test_prestador_cnpj_repetido_409(criar):
    _, prestador, _ = criar
    cnpj = _cnpj()
    primeiro = prestador(cnpj=cnpj)
    r = prestador(cnpj=_pontuado(cnpj))
    assert r.status_code == 409
    assert cnpj in r.json()["detail"] and str(primeiro.json()["id"]) in r.json()["detail"]


# ---------- contratos ----------

def test_contrato_cria_e_lista_com_dados_para_seletor(criar):
    tomador, prestador, contrato = criar
    t, p = tomador().json(), prestador().json()
    r = contrato(t["id"], p["id"], vigencia_inicio="2026-01-01", vigencia_fim="2026-12-31")
    assert r.status_code == 201
    corpo = r.json()
    assert set(corpo) == {"id", "tomador_id", "prestador_id", "ativo", "vigencia_inicio", "vigencia_fim", "criado_em",
                          "perfil_jornada", "proprio", "tomador_nome", "tomador_ativo", "prestador_razao_social", "prestador_cnpj",
                          "prestador_ativo", "acesso_prestador", "perfil_jornada_nome", "perfil_jornada_visivel"}
    assert corpo["ativo"] is True and corpo["vigencia_inicio"] == "2026-01-01"
    assert corpo["vigencia_fim"] == "2026-12-31"
    assert corpo["tomador_nome"] == t["nome"] and corpo["prestador_razao_social"] == p["razao_social"]
    assert corpo["prestador_cnpj"] == p["cnpj"]
    item = next(c for c in client.get("/contratos").json() if c["id"] == corpo["id"])
    assert item == corpo


def test_contrato_vigencia_opcional(criar):
    tomador, prestador, contrato = criar
    r = contrato(tomador().json()["id"], prestador().json()["id"])
    assert r.status_code == 201 and r.json()["vigencia_inicio"] is None and r.json()["vigencia_fim"] is None


def test_contrato_vigencia_invertida_422_e_igual_vale(criar):
    tomador, prestador, contrato = criar
    t, p = tomador().json()["id"], prestador().json()["id"]
    r = contrato(t, p, vigencia_inicio="2026-06-02", vigencia_fim="2026-06-01")
    assert r.status_code == 422 and "vigencia_fim" in r.text
    assert client.get("/contratos", params={"tomador_id": t}).json() == []  # nada foi gravado
    assert contrato(t, p, vigencia_inicio="2026-06-01", vigencia_fim="2026-06-01").status_code == 201


def test_contrato_par_repetido_409(criar):
    tomador, prestador, contrato = criar
    t, p = tomador().json()["id"], prestador().json()["id"]
    primeiro = contrato(t, p)
    r = contrato(t, p)
    assert r.status_code == 409
    assert str(primeiro.json()["id"]) in r.json()["detail"] and f"tomador {t}" in r.json()["detail"]


def test_contrato_inexistentes_404(criar):
    tomador, prestador, contrato = criar
    t, p = tomador().json()["id"], prestador().json()["id"]
    r = contrato(999999999, p)
    assert r.status_code == 404 and "tomador 999999999" in r.json()["detail"]
    r = contrato(t, 999999999)
    assert r.status_code == 404 and "prestador 999999999" in r.json()["detail"]


def test_contrato_id_fora_do_bigint_422(criar):
    _, _, contrato = criar
    assert contrato(2 ** 70, 1).status_code == 422
    assert contrato(0, 1).status_code == 422
    assert client.get("/contratos", params={"tomador_id": 2 ** 70}).status_code == 422


def test_contratos_filtros(criar):
    tomador, prestador, contrato = criar
    t1, t2 = tomador().json()["id"], tomador().json()["id"]
    p1, p2 = prestador().json()["id"], prestador().json()["id"]
    c11 = contrato(t1, p1).json()["id"]
    c12 = contrato(t1, p2).json()["id"]
    c21 = contrato(t2, p1).json()["id"]

    def ids(**filtros):
        r = client.get("/contratos", params=filtros)
        assert r.status_code == 200
        return [c["id"] for c in r.json()]
    assert ids(tomador_id=t1) == [c11, c12]
    assert ids(prestador_id=p1) == [c11, c21]
    assert ids(tomador_id=t1, prestador_id=p1) == [c11]
    assert ids(tomador_id=t2, prestador_id=p2) == []
    assert ids(tomador_id=999999999) == []
    assert {c11, c12, c21} <= set(ids())


def test_contrato_nao_ativo_aparece_com_flags(orgs):
    c = orgs.contrato(ativo=False, tomador_ativo=True, prestador_ativo=False)
    item = next(x for x in client.get("/contratos").json() if x["id"] == c)
    assert item["ativo"] is False and item["tomador_ativo"] is True and item["prestador_ativo"] is False


def test_corrida_dois_posts_iguais_geram_um_201_e_varios_409():
    """A unicidade é do banco: criações simultâneas do mesmo tomador nunca viram 500 nem duplicam."""
    from concurrent.futures import ThreadPoolExecutor
    nome = _nome()
    with ThreadPoolExecutor(8) as pool:
        respostas = list(pool.map(lambda _: client.post("/tomadores", json={"nome": nome}), range(8)))
    ids = [r.json()["id"] for r in respostas if r.status_code == 201]
    try:
        assert sorted(r.status_code for r in respostas) == [201] + [409] * 7
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (ids,))
