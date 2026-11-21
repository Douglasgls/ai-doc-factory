"""Empresa própria (empresa solo): POST /empresas-proprias, o acesso do admin (nível prestador) ao próprio contrato,
isolamento e a troca do perfil de jornada. Contra o Postgres real; só valores falsos. Reaproveita a fixture `mundo` de
tests/test_terceirizadas.py (que apaga o que foi criado: a empresa criada pela API é registrada nela)."""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.routers.lotes import actions as lotes_actions
from test_conformidade_api import CPF1, campos_pessoa, novo_lote  # noqa: F401  (novo_lote é fixture)
from test_terceirizadas import _aceitar, _email, _h_id, mundo  # noqa: F401  (mundo é fixture)

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)


@pytest.fixture
def criar(mundo):
    """POST /empresas-proprias como plataforma; registra tomador, prestador e e-mail para a limpeza."""
    plat = _h_id(mundo.usuario())

    def _f(cnpj=None, razao=None, email=None, headers=None):
        cnpj = cnpj or mundo.cnpj()
        email = email or _email()
        mundo.emails.append(email)
        r = client.post("/empresas-proprias", headers=headers or plat, json={
            "cnpj": cnpj, "razao_social": razao or f"Empresa Solo {uuid.uuid4().hex}", "email_admin": email})
        if r.status_code == 201:
            mundo.tomadores.append(r.json()["tomador"]["id"])
            mundo.prestadores.append(r.json()["prestador"]["id"])
        return r
    _f.plat = plat
    return _f


def _contagens(mundo, cnpj):
    return tuple(mundo.db.execute(f"SELECT count(*) FROM {t} WHERE cnpj = %s", (cnpj,)).fetchone()[0]
                 for t in ("tomador", "prestador"))


# ---------- criação ----------

def test_cria_empresa_propria_com_contrato_proprio_e_convite(mundo, criar):
    cnpj = mundo.cnpj()
    r = criar(cnpj, razao="Padaria Solo Ltda")
    assert r.status_code == 201
    j = r.json()
    assert j["contrato"]["proprio"] is True and j["contrato"]["ativo"] is True
    assert j["tomador"]["cnpj"] == cnpj == j["prestador"]["cnpj"]
    assert j["tomador"]["nome"] == "Padaria Solo Ltda" and j["prestador"]["nome"] == "Padaria Solo Ltda"
    assert j["acesso"] == "convite_criado" and j["convite"]["token"]
    linha = mundo.db.execute("SELECT proprio, tomador_id, prestador_id, perfil_jornada FROM contrato WHERE id = %s",
                             (j["contrato"]["id"],)).fetchone()
    assert linha == (True, j["tomador"]["id"], j["prestador"]["id"], "clt_padrao")
    convite = mundo.db.execute("SELECT nivel, papel, prestador_id, tomador_id FROM convite WHERE id = %s",
                               (j["convite"]["id"],)).fetchone()
    assert convite == ("prestador", "admin", j["prestador"]["id"], None)
    # a plataforma vê o campo em GET /contratos
    contratos = {c["id"]: c for c in client.get("/contratos", headers=criar.plat).json()}
    assert contratos[j["contrato"]["id"]]["proprio"] is True


def test_reaproveita_tomador_e_prestador_do_mesmo_cnpj(mundo, criar):
    cnpj = mundo.cnpj()
    t = mundo.db.execute("INSERT INTO tomador (nome, cnpj) VALUES (%s, %s) RETURNING id",
                         (f"Nome Antigo {uuid.uuid4().hex}", cnpj)).fetchone()[0]
    mundo.tomadores.append(t)
    r = criar(cnpj, razao="Nome Novo Ltda")
    assert r.status_code == 201 and r.json()["tomador"]["id"] == t
    assert r.json()["tomador"]["nome"].startswith("Nome Antigo")  # não renomeia o que já existia
    assert _contagens(mundo, cnpj) == (1, 1)


def test_validacoes_e_permissao(mundo, criar):
    corpo = {"cnpj": mundo.cnpj(), "razao_social": "X Ltda", "email_admin": _email()}
    assert client.post("/empresas-proprias", headers=criar.plat, json={**corpo, "cnpj": "11222333000182"}
                       ).status_code == 422  # dígitos verificadores
    assert client.post("/empresas-proprias", headers=criar.plat, json={**corpo, "email_admin": "sem-arroba"}
                       ).status_code == 422
    assert client.post("/empresas-proprias", json=corpo).status_code == 401
    _, uid = mundo.admin_tomador()
    assert client.post("/empresas-proprias", headers=_h_id(uid), json=corpo).status_code == 403
    p = mundo.prestador()
    uid = mundo.usuario("prestador", "admin", prestador_id=p)
    assert client.post("/empresas-proprias", headers=_h_id(uid), json=corpo).status_code == 403
    assert _contagens(mundo, corpo["cnpj"]) == (0, 0)


def test_409_cnpj_ja_e_empresa_propria(mundo, criar):
    cnpj = mundo.cnpj()
    assert criar(cnpj).status_code == 201
    r = criar(cnpj)
    assert r.status_code == 409 and "próprio" in r.json()["detail"]
    assert mundo.db.execute("SELECT count(*) FROM contrato c JOIN prestador p ON p.id = c.prestador_id "
                            "WHERE p.cnpj = %s", (cnpj,)).fetchone()[0] == 1


def test_409_cnpj_ja_e_prestador_de_contrato_nao_proprio(mundo, criar):
    t, p = mundo.tomador(), mundo.prestador()
    mundo.contrato(t, p)
    cnpj = mundo.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (p,)).fetchone()[0]
    r = criar(cnpj)
    assert r.status_code == 409 and "não próprios" in r.json()["detail"]
    assert _contagens(mundo, cnpj) == (0, 1)  # nada foi criado (nem o tomador)
    # terceirizar uma empresa própria também é recusado, para o admin dela não ver lotes de outro cliente
    cnpj2 = mundo.cnpj()
    assert criar(cnpj2).status_code == 201
    _, uid = mundo.admin_tomador()
    r2 = mundo.terceirizada(_h_id(uid), cnpj_=cnpj2)
    assert r2.status_code == 409 and "empresa própria" in r2.json()["detail"]


def test_409_organizacao_desativada_e_nome_de_tomador_repetido(mundo, criar):
    p = mundo.prestador(ativo=False)
    cnpj = mundo.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (p,)).fetchone()[0]
    r = criar(cnpj)
    assert r.status_code == 409 and "desativada" in r.json()["detail"]
    cnpj2 = mundo.cnpj()
    t = mundo.db.execute("INSERT INTO tomador (nome, cnpj, ativo) VALUES (%s, %s, false) RETURNING id",
                         (f"Inativo {uuid.uuid4().hex}", cnpj2)).fetchone()[0]
    mundo.tomadores.append(t)
    r = criar(cnpj2)
    assert r.status_code == 409 and "desativada" in r.json()["detail"]
    assert _contagens(mundo, cnpj2) == (1, 0)
    nome = f"Nome Repetido {uuid.uuid4().hex}"
    mundo.db.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id", (nome,))
    mundo.tomadores.extend(l[0] for l in mundo.db.execute("SELECT id FROM tomador WHERE nome = %s", (nome,)))
    cnpj3 = mundo.cnpj()
    r = criar(cnpj3, razao=nome.upper())
    assert r.status_code == 409 and "nome" in r.json()["detail"]
    assert _contagens(mundo, cnpj3) == (0, 0)


# ---------- acesso do admin da empresa própria ----------

def _ids_documentos(agrupados) -> set:
    """GET /documentos devolve os documentos agrupados por tipo: junta os ids de todos os grupos."""
    achados = set()

    def varrer(no):
        if isinstance(no, dict):
            if "id" in no and "estado" in no:
                achados.add(no["id"])
            else:
                for v in no.values():
                    varrer(v)
        elif isinstance(no, list):
            for v in no:
                varrer(v)
    varrer(agrupados)
    return achados


@pytest.fixture
def envio(monkeypatch):
    enfileirados, criados = [], []
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda r, fila, payload, *a, **k: enfileirados.append(payload))

    def enviar(headers, contrato_id=None):
        form = {} if contrato_id is None else {"contrato_id": str(contrato_id)}
        r = client.post("/lotes", headers=headers, data=form, files={
            "arquivo": ("a.pdf", b"%PDF-1.4 propria " + uuid.uuid4().hex.encode(), "application/pdf")})
        if r.status_code == 200:
            criados.append(r.json()["lote_id"])
        return r
    yield enviar, enfileirados
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (criados,))


def test_aceita_convite_e_admin_sobe_lote_no_proprio_contrato(mundo, criar, envio):
    enviar, jobs = envio
    r = criar()
    assert r.status_code == 201
    aceite = _aceitar(r.json()["convite"]["token"], nome="Dona da Empresa")
    assert aceite.status_code == 200
    h = {"Authorization": "Bearer " + aceite.json()["access_token"]}
    contratos = client.get("/contratos", headers=h).json()
    assert [(c["id"], c["proprio"]) for c in contratos] == [(r.json()["contrato"]["id"], True)]
    assert enviar(h).status_code == 422  # contrato continua obrigatório na API (a tela o preenche sozinha)
    ok = enviar(h, r.json()["contrato"]["id"])
    assert ok.status_code == 200 and len(jobs) == 1
    assert client.get(f"/lotes/{ok.json()['lote_id']}", headers=h).status_code == 200


def _admin(mundo, r):
    return _h_id(mundo.usuario("prestador", "admin", prestador_id=r.json()["prestador"]["id"]))


def test_admin_ve_so_a_propria_empresa_com_score(mundo, criar, novo_lote):
    x, y = criar(), criar()
    hx = _admin(mundo, x)
    cnpj_x, cnpj_y = x.json()["prestador"]["cnpj"], y.json()["prestador"]["cnpj"]
    lote_x, ids_x = novo_lote([("aso", "classificado", campos_pessoa(cnpj_x, CPF1)),
                           ("holerite", "classificado", campos_pessoa(cnpj_x, CPF1))])
    lote_y, ids_y = novo_lote([("aso", "classificado", campos_pessoa(cnpj_y, CPF1))])
    mundo.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (x.json()["contrato"]["id"], lote_x))
    mundo.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (y.json()["contrato"]["id"], lote_y))
    lista = client.get("/empresas", headers=hx).json()
    assert [e["cnpj"] for e in lista] == [cnpj_x]
    assert isinstance(lista[0]["score"], int) and lista[0]["documentos_por_tipo"] == {"aso": 1, "holerite": 1}
    assert client.get(f"/empresas/{cnpj_x}/conformidade", headers=hx).status_code == 200
    # nada da empresa Y
    assert client.get(f"/empresas/{cnpj_y}/conformidade", headers=hx).status_code == 404
    assert client.get(f"/lotes/{lote_y}", headers=hx).status_code == 404
    assert client.get(f"/lotes/{lote_y}/conformidade", headers=hx).status_code == 404
    assert client.get(f"/documentos/{ids_y[0]}", headers=hx).status_code == 404
    assert _ids_documentos(client.get("/documentos", headers=hx).json()) == set(ids_x)
    assert [c["id"] for c in client.get("/contratos", headers=hx).json()] == [x.json()["contrato"]["id"]]


def test_admin_nao_ve_terceirizadas_nem_contratos_de_outros(mundo, criar, novo_lote):
    x = criar()
    hx = _admin(mundo, x)
    t, p = mundo.tomador(), mundo.prestador()
    c = mundo.contrato(t, p)
    cnpj_p = mundo.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (p,)).fetchone()[0]
    lote, _ = novo_lote([("aso", "classificado", campos_pessoa(cnpj_p, CPF1))])
    mundo.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (c, lote))
    assert client.get(f"/lotes/{lote}", headers=hx).status_code == 404
    assert client.get("/empresas", headers=hx).json() == []
    assert client.get(f"/empresas/{cnpj_p}/conformidade", headers=hx).status_code == 404
    assert _ids_documentos(client.get("/documentos", headers=hx).json()) == set()
    # o admin da terceirizada P não vê o contrato próprio de X
    hp = _h_id(mundo.usuario("prestador", "admin", prestador_id=p))
    assert [ct["id"] for ct in client.get("/contratos", headers=hp).json()] == [c]
    # contrato dos outros no upload: 404 (o do próprio é 200, testado acima)
    mundo.db.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_post_contratos_com_outro_tomador_para_empresa_propria_da_409(mundo, criar, novo_lote):
    x = criar()
    hx = _admin(mundo, x)
    outro = mundo.tomador()
    antes = mundo.db.execute("SELECT count(*) FROM contrato WHERE prestador_id = %s",
                             (x.json()["prestador"]["id"],)).fetchone()[0]
    r = client.post("/contratos", headers=criar.plat, json={"tomador_id": outro,
                                                            "prestador_id": x.json()["prestador"]["id"]})
    assert r.status_code == 409 and "empresa própria" in r.json()["detail"]
    assert mundo.db.execute("SELECT count(*) FROM contrato WHERE prestador_id = %s",
                            (x.json()["prestador"]["id"],)).fetchone()[0] == antes == 1
    assert [c["id"] for c in client.get("/contratos", headers=hx).json()] == [x.json()["contrato"]["id"]]
    # contrato comum entre outros continua podendo ser criado
    assert client.post("/contratos", headers=criar.plat, json={"tomador_id": outro, "prestador_id": mundo.prestador()}
                       ).status_code == 201


# ---------- perfil de jornada ----------

@pytest.fixture
def perfil():
    nome = "solo_" + uuid.uuid4().hex[:8]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                     "VALUES (%s, 'jornada_diaria_min', 420, 'min', 'acordo de teste')", (nome,))
        yield nome
        conn.execute("DELETE FROM perfil_jornada WHERE perfil = %s", (nome,))


def test_admin_da_empresa_propria_troca_o_perfil_do_proprio_contrato(mundo, criar, perfil):
    x = criar()
    cid = x.json()["contrato"]["id"]
    h = _admin(mundo, x)
    r = client.put(f"/contratos/{cid}/perfil-jornada", headers=h, json={"perfil": perfil})
    assert r.status_code == 200 and r.json()["perfil_jornada"] == perfil and r.json()["proprio"] is True
    assert mundo.db.execute("SELECT perfil_jornada FROM contrato WHERE id = %s", (cid,)).fetchone()[0] == perfil
    assert client.put(f"/contratos/{cid}/perfil-jornada", headers=h, json={"perfil": "nao_existe"}).status_code == 404
    # leitura dos perfis liberada; escrita de perfil continua só da plataforma
    nomes = {p["perfil"]: p for p in client.get("/perfis-jornada", headers=h).json()}
    assert nomes[perfil]["contratos"] == 1 and "clt_padrao" in nomes  # `contratos` conta só o escopo dele
    assert client.get(f"/perfis-jornada/{perfil}", headers=h).status_code == 200
    corpo = {"parametros": [{"parametro": "jornada_diaria_min", "valor": 1, "base_legal": "x"}]}
    assert client.put(f"/perfis-jornada/{perfil}", headers=h, json=corpo).status_code == 403
    assert client.put("/perfis-jornada/criado_pelo_prestador", headers=h, json=corpo).status_code == 403


def test_membro_e_contrato_nao_proprio_nao_trocam_o_perfil(mundo, criar, perfil):
    x, y = criar(), criar()
    cx, cy = x.json()["contrato"]["id"], y.json()["contrato"]["id"]
    membro = _h_id(mundo.usuario("prestador", "membro", prestador_id=x.json()["prestador"]["id"]))
    corpo = {"perfil": perfil}
    assert client.put(f"/contratos/{cx}/perfil-jornada", headers=membro, json=corpo).status_code == 403
    assert client.get("/perfis-jornada", headers=membro).status_code == 403
    hx = _admin(mundo, x)
    assert client.put(f"/contratos/{cy}/perfil-jornada", headers=hx, json=corpo).status_code == 403  # contrato de outra
    assert client.put("/contratos/999999999/perfil-jornada", headers=hx, json=corpo).status_code == 403
    # terceirizada comum: admin do prestador, contrato dele mas não próprio
    t, p = mundo.tomador(), mundo.prestador()
    c = mundo.contrato(t, p)
    hp = _h_id(mundo.usuario("prestador", "admin", prestador_id=p))
    assert client.put(f"/contratos/{c}/perfil-jornada", headers=hp, json=corpo).status_code == 403
    assert client.get("/perfis-jornada", headers=hp).status_code == 403
    # admin do tomador também não
    _, uid = mundo.admin_tomador()
    assert client.put(f"/contratos/{cx}/perfil-jornada", headers=_h_id(uid), json=corpo).status_code == 403
    assert mundo.db.execute("SELECT perfil_jornada FROM contrato WHERE id = ANY(%s)", ([cx, cy, c],)).fetchall() \
        == [("clt_padrao",)] * 3
    # a plataforma continua podendo
    assert client.put(f"/contratos/{c}/perfil-jornada", headers=criar.plat, json=corpo).status_code == 200
