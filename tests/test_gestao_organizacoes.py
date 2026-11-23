"""Gestão de organizações: PATCH {ativo} de tomador, prestador, contrato e usuário; DELETE de convite pendente.
Contra o Postgres real; só valores falsos. Cada teste cria o que usa e apaga no fim."""
import time
import uuid

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.routers.lotes import actions as lotes_actions
from conftest import cnpj_valido

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

INEXISTENTE = 2 ** 62
NAO_ENCONTRADO = {"detail": "convite inválido, usado ou expirado"}


def _h_id(uid: int) -> dict:
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": str(uid), "iat": agora - 5, "exp": agora + 600}, config.AUTH_SEGREDO, algorithm="HS256")}


def _email() -> str:
    return f"gestao-{uuid.uuid4().hex}@exemplo.invalid"


class Mundo:
    pass


@pytest.fixture
def mundo(monkeypatch):
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: None)
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    m = Mundo()
    m.db, m.emails, m.tomadores, m.prestadores, m.contratos, m.lotes = conn, [], [], [], [], []

    def tomador():
        i = conn.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id", (f"Tomador {uuid.uuid4().hex}",)).fetchone()[0]
        m.tomadores.append(i)
        return i

    def prestador():
        i = conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING id",
                         (cnpj_valido(uuid.uuid4().int), f"Prestador {uuid.uuid4().hex}")).fetchone()[0]
        m.prestadores.append(i)
        return i

    def contrato(t, p):
        i = conn.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s) RETURNING id", (t, p)).fetchone()[0]
        m.contratos.append(i)
        return i

    def usuario(nivel="plataforma", papel="admin", tomador_id=None, prestador_id=None):
        email = _email()
        m.emails.append(email)
        return conn.execute(
            "INSERT INTO usuario (email, nome, senha_hash, nivel, papel, tomador_id, prestador_id) "
            "VALUES (%s, 'Pessoa de Teste', 'x', %s, %s, %s, %s) RETURNING id",
            (email, nivel, papel, tomador_id, prestador_id)).fetchone()[0]

    def ativo(tabela, id_):
        return conn.execute(f"SELECT ativo FROM {tabela} WHERE id = %s", (id_,)).fetchone()[0]

    m.tomador, m.prestador, m.contrato, m.usuario, m.ativo = tomador, prestador, contrato, usuario, ativo
    m.t1, m.p1, m.t2, m.p2 = tomador(), prestador(), tomador(), prestador()
    m.c1, m.c2 = contrato(m.t1, m.p1), contrato(m.t2, m.p2)
    m.plat = usuario()
    m.h = _h_id(m.plat)
    try:
        yield m
    finally:
        conn.execute("DELETE FROM lote WHERE contrato_id = ANY(%s)", (m.contratos,))
        conn.execute("DELETE FROM convite WHERE lower(email) = ANY(%s) OR tomador_id = ANY(%s) OR prestador_id = ANY(%s)",
                     (m.emails, m.tomadores, m.prestadores))
        conn.execute("DELETE FROM usuario WHERE lower(email) = ANY(%s) OR tomador_id = ANY(%s) OR prestador_id = ANY(%s)",
                     (m.emails, m.tomadores, m.prestadores))
        conn.execute("DELETE FROM contrato WHERE id = ANY(%s)", (m.contratos,))
        conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (m.tomadores,))
        conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (m.prestadores,))
        conn.close()


# ---------- tomador, prestador e contrato ----------

def _item(lista, id_):
    return next(x for x in lista if x["id"] == id_)


@pytest.mark.parametrize("rota,tabela,lista", [("tomadores", "tomador", "/tomadores"),
                                               ("prestadores", "prestador", "/prestadores"),
                                               ("contratos", "contrato", "/contratos")])
def test_plataforma_desativa_e_reativa_e_repetir_e_idempotente(mundo, rota, tabela, lista):
    id_ = {"tomador": mundo.t1, "prestador": mundo.p1, "contrato": mundo.c1}[tabela]
    for ativo in (False, False, True, True):
        r = client.patch(f"/{rota}/{id_}", headers=mundo.h, json={"ativo": ativo})
        assert r.status_code == 200, r.text
        assert r.json()["ativo"] is ativo and mundo.ativo(tabela, id_) is ativo
        # mesmo formato do GET de listagem
        assert r.json() == _item(client.get(lista, headers=mundo.h).json(), id_)


@pytest.mark.parametrize("rota", ["tomadores", "prestadores", "contratos"])
def test_patch_de_organizacao_inexistente_404(mundo, rota):
    assert client.patch(f"/{rota}/{INEXISTENTE}", headers=mundo.h, json={"ativo": False}).status_code == 404


@pytest.mark.parametrize("corpo", [{}, {"ativo": "talvez"}, {"ativo": "false"}, {"ativo": 1}, {"ativo": None}])
def test_patch_com_corpo_invalido_422(mundo, corpo):
    assert client.patch(f"/tomadores/{mundo.t1}", headers=mundo.h, json=corpo).status_code == 422
    assert mundo.ativo("tomador", mundo.t1) is True


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
@pytest.mark.parametrize("papel", ["admin", "membro"])
def test_so_plataforma_altera_organizacoes_403(mundo, nivel, papel):
    vinculo = {"tomador_id": mundo.t1} if nivel == "tomador" else {"prestador_id": mundo.p1}
    h = _h_id(mundo.usuario(nivel=nivel, papel=papel, **vinculo))
    for rota, id_, tabela in (("tomadores", mundo.t1, "tomador"), ("prestadores", mundo.p1, "prestador"),
                              ("contratos", mundo.c1, "contrato")):
        assert client.patch(f"/{rota}/{id_}", headers=h, json={"ativo": False}).status_code == 403
        assert mundo.ativo(tabela, id_) is True


def test_patch_sem_token_401(mundo):
    assert client.patch(f"/tomadores/{mundo.t1}", json={"ativo": False}).status_code == 401


def test_contrato_desativado_some_do_escopo_do_prestador_e_do_upload(mundo):
    h = _h_id(mundo.usuario(nivel="prestador", papel="admin", prestador_id=mundo.p1))
    assert mundo.c1 in {c["id"] for c in client.get("/contratos", headers=h).json()}
    pdf = b"%PDF-1.4 gestao " + uuid.uuid4().hex.encode()
    ok = client.post("/lotes", headers=h, files={"arquivo": ("a.pdf", pdf, "application/pdf")},
                     data={"contrato_id": str(mundo.c1)})
    assert ok.status_code == 200, ok.text
    assert client.patch(f"/contratos/{mundo.c1}", headers=mundo.h, json={"ativo": False}).status_code == 200
    assert mundo.c1 not in {c["id"] for c in client.get("/contratos", headers=h).json()}
    recusado = client.post("/lotes", headers=h, files={"arquivo": ("b.pdf", pdf + b"2", "application/pdf")},
                           data={"contrato_id": str(mundo.c1)})
    assert recusado.status_code == 404
    # o lote que já existia deixa de ser visível ao prestador (escopo exige contrato ativo)
    assert client.get(f"/lotes/{ok.json()['lote_id']}", headers=h).status_code == 404
    # a plataforma continua vendo; reativar devolve o acesso
    assert client.get(f"/lotes/{ok.json()['lote_id']}", headers=mundo.h).status_code == 200
    client.patch(f"/contratos/{mundo.c1}", headers=mundo.h, json={"ativo": True})
    assert client.get(f"/lotes/{ok.json()['lote_id']}", headers=h).status_code == 200


# ---------- usuários ----------

def _patch_usuario(h, uid, ativo):
    return client.patch(f"/usuarios/{uid}", headers=h, json={"ativo": ativo})


def test_plataforma_desativa_qualquer_usuario_e_devolve_formato_da_listagem(mundo):
    alvo = mundo.usuario(nivel="tomador", papel="membro", tomador_id=mundo.t1)
    r = _patch_usuario(mundo.h, alvo, False)
    assert r.status_code == 200 and r.json()["ativo"] is False and mundo.ativo("usuario", alvo) is False
    assert set(r.json()) == {"id", "nome", "email", "nivel", "papel", "ativo", "criado_em"}
    assert r.json() == _item(client.get("/usuarios", headers=mundo.h).json(), alvo)
    assert _patch_usuario(mundo.h, alvo, False).status_code == 200  # idempotente
    assert _patch_usuario(mundo.h, alvo, True).json()["ativo"] is True


def test_admin_do_tomador_so_mexe_na_propria_organizacao(mundo):
    admin = mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t1)
    h = _h_id(admin)
    colega = mundo.usuario(nivel="tomador", papel="membro", tomador_id=mundo.t1)
    de_fora = mundo.usuario(nivel="tomador", papel="membro", tomador_id=mundo.t2)
    prestador = mundo.usuario(nivel="prestador", papel="membro", prestador_id=mundo.p1)
    assert _patch_usuario(h, colega, False).status_code == 200 and mundo.ativo("usuario", colega) is False
    inexistente = _patch_usuario(h, INEXISTENTE, False)
    for alvo in (de_fora, prestador, mundo.plat):
        r = _patch_usuario(h, alvo, False)
        assert r.status_code == 404 and r.json() == inexistente.json()
        assert mundo.ativo("usuario", alvo) is True


def test_admin_do_prestador_so_mexe_na_propria_organizacao(mundo):
    h = _h_id(mundo.usuario(nivel="prestador", papel="admin", prestador_id=mundo.p1))
    colega = mundo.usuario(nivel="prestador", papel="membro", prestador_id=mundo.p1)
    de_fora = mundo.usuario(nivel="prestador", papel="membro", prestador_id=mundo.p2)
    assert _patch_usuario(h, colega, False).status_code == 200
    assert _patch_usuario(h, de_fora, False).status_code == 404 and mundo.ativo("usuario", de_fora) is True


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_membro_nao_gerencia_usuarios_403(mundo, nivel):
    vinculo = {"tomador_id": mundo.t1} if nivel == "tomador" else {"prestador_id": mundo.p1}
    membro = mundo.usuario(nivel=nivel, papel="membro", **vinculo)
    colega = mundo.usuario(nivel=nivel, papel="membro", **vinculo)
    assert _patch_usuario(_h_id(membro), colega, False).status_code == 403
    assert _patch_usuario(_h_id(membro), INEXISTENTE, False).status_code == 403
    assert mundo.ativo("usuario", colega) is True


@pytest.mark.parametrize("nivel", ["plataforma", "tomador", "prestador"])
def test_ninguem_desativa_a_si_mesmo_409(mundo, nivel):
    vinculo = {"tomador_id": mundo.t1} if nivel == "tomador" else {"prestador_id": mundo.p1} if nivel == "prestador" else {}
    eu = mundo.usuario(nivel=nivel, papel="admin", **vinculo)
    r = _patch_usuario(_h_id(eu), eu, False)
    assert r.status_code == 409 and mundo.ativo("usuario", eu) is True
    assert _patch_usuario(_h_id(eu), eu, True).status_code == 200  # reafirmar ativo é inofensivo


def test_usuario_inexistente_404_para_plataforma(mundo):
    assert _patch_usuario(mundo.h, INEXISTENTE, False).status_code == 404


def test_usuario_sem_token_ou_com_corpo_invalido(mundo):
    alvo = mundo.usuario(nivel="tomador", papel="membro", tomador_id=mundo.t1)
    assert client.patch(f"/usuarios/{alvo}", json={"ativo": False}).status_code == 401
    assert client.patch(f"/usuarios/{alvo}", headers=mundo.h, json={}).status_code == 422


def test_token_de_usuario_desativado_e_recusado(mundo):
    alvo = mundo.usuario(nivel="tomador", papel="membro", tomador_id=mundo.t1)
    h = _h_id(alvo)  # token emitido antes da desativação
    assert client.get("/auth/me", headers=h).status_code == 200
    assert _patch_usuario(mundo.h, alvo, False).status_code == 200
    for caminho in ("/auth/me", "/contratos", "/tipos"):
        assert client.get(caminho, headers=h).status_code == 401
    assert _patch_usuario(mundo.h, alvo, True).status_code == 200
    assert client.get("/auth/me", headers=h).status_code == 200


# ---------- convites ----------

def _convidar(h, **kw):
    corpo = {"email": _email(), "nivel": "tomador", "papel": "membro", **kw}
    r = client.post("/convites", headers=h, json=corpo)
    assert r.status_code == 201, r.text
    return r.json()


def _estado(h, id_):
    return _item(client.get("/convites", headers=h).json(), id_)["estado"]


def test_plataforma_revoga_convite_pendente_e_o_token_morre(mundo):
    convite = _convidar(mundo.h, tomador_id=mundo.t1)
    token = convite["token"]
    assert client.get(f"/convites/{token}").status_code == 200
    r = client.delete(f"/convites/{convite['id']}", headers=mundo.h)
    assert r.status_code == 204 and r.content == b""
    assert _estado(mundo.h, convite["id"]) == "expirado"
    consulta = client.get(f"/convites/{token}")
    aceite = client.post(f"/convites/{token}/aceitar", json={"nome": "Fulano de Tal", "senha": "senha-falsa-longa"})
    assert consulta.status_code == aceite.status_code == 404
    assert consulta.json() == aceite.json() == NAO_ENCONTRADO
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (convite["email"],)).fetchone()[0] == 0
    # revogar de novo não quebra, e o e-mail pode ser convidado outra vez
    assert client.delete(f"/convites/{convite['id']}", headers=mundo.h).status_code == 204
    assert client.post("/convites", headers=mundo.h,
                       json={"email": convite["email"], "nivel": "tomador", "papel": "membro",
                             "tomador_id": mundo.t1}).status_code == 201


def test_revogar_libera_o_prestador_para_novo_convite_e_acesso_prestador(mundo):
    convite = _convidar(mundo.h, nivel="prestador", papel="admin", prestador_id=mundo.p1)
    contrato = lambda: _item(client.get("/contratos", headers=mundo.h).json(), mundo.c1)  # noqa: E731
    assert contrato()["acesso_prestador"] == "convite_pendente"
    assert client.delete(f"/convites/{convite['id']}", headers=mundo.h).status_code == 204
    assert contrato()["acesso_prestador"] == "sem_acesso"
    from app.escopo import prestador_tem_convite_pendente
    from app.database import SessionLocal
    with SessionLocal() as s:
        assert prestador_tem_convite_pendente(s, mundo.p1) is False


def test_convite_usado_nao_revoga_409(mundo):
    convite = _convidar(mundo.h, tomador_id=mundo.t1)
    aceite = client.post(f"/convites/{convite['token']}/aceitar", json={"nome": "Fulano de Tal", "senha": "senha-falsa-longa"})
    assert aceite.status_code == 200, aceite.text
    assert client.delete(f"/convites/{convite['id']}", headers=mundo.h).status_code == 409
    assert _estado(mundo.h, convite["id"]) == "usado"


def test_convite_inexistente_404(mundo):
    assert client.delete(f"/convites/{INEXISTENTE}", headers=mundo.h).status_code == 404


def test_admin_revoga_so_convites_da_propria_organizacao(mundo):
    admin = mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t1)
    h = _h_id(admin)
    proprio = _convidar(h, tomador_id=mundo.t1)
    da_plataforma = _convidar(mundo.h, tomador_id=mundo.t1)  # criado por quem não é da organização
    outro_admin = mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t2)
    de_fora = _convidar(_h_id(outro_admin), tomador_id=mundo.t2)
    assert client.delete(f"/convites/{proprio['id']}", headers=h).status_code == 204
    # mesma regra de GET /convites: só os criados por usuários da própria organização
    visiveis = {c["id"] for c in client.get("/convites", headers=h).json()}
    assert da_plataforma["id"] not in visiveis and de_fora["id"] not in visiveis
    for alheio in (da_plataforma, de_fora):
        assert client.delete(f"/convites/{alheio['id']}", headers=h).status_code == 404
        assert _estado(mundo.h, alheio["id"]) == "pendente"
        assert client.get(f"/convites/{alheio['token']}").status_code == 200


def test_admin_do_prestador_revoga_convite_proprio(mundo):
    h = _h_id(mundo.usuario(nivel="prestador", papel="admin", prestador_id=mundo.p1))
    convite = _convidar(h, nivel="prestador", prestador_id=mundo.p1)
    assert client.delete(f"/convites/{convite['id']}", headers=h).status_code == 204
    assert client.get(f"/convites/{convite['token']}").status_code == 404


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_membro_nao_revoga_convite_403(mundo, nivel):
    vinculo = {"tomador_id": mundo.t1} if nivel == "tomador" else {"prestador_id": mundo.p1}
    convite = _convidar(mundo.h, nivel=nivel, **vinculo)
    h = _h_id(mundo.usuario(nivel=nivel, papel="membro", **vinculo))
    assert client.delete(f"/convites/{convite['id']}", headers=h).status_code == 403
    assert client.get(f"/convites/{convite['token']}").status_code == 200


def test_revogar_sem_token_401(mundo):
    assert client.delete("/convites/1").status_code == 401


# ---------- reemitir convite (novo link) ----------

def _reemitir(h, id_):
    return client.post(f"/convites/{id_}/reemitir", headers=h)


def _vale(token) -> bool:
    return client.get(f"/convites/{token}").status_code == 200


def test_plataforma_reemite_e_o_link_antigo_deixa_de_valer(mundo):
    antigo = _convidar(mundo.h, nivel="prestador", papel="admin", prestador_id=mundo.p1)
    r = _reemitir(mundo.h, antigo["id"])
    assert r.status_code == 201, r.text
    novo = r.json()
    assert novo["id"] != antigo["id"] and novo["token"] != antigo["token"]
    assert (novo["email"], novo["papel"]) == (antigo["email"], "admin")
    assert not _vale(antigo["token"]) and _vale(novo["token"])
    assert _estado(mundo.h, antigo["id"]) == "expirado" and _estado(mundo.h, novo["id"]) == "pendente"
    publico = client.get(f"/convites/{novo['token']}").json()
    assert publico["email"] == antigo["email"] and publico["nivel"] == "prestador"
    # o token novo vem só na resposta: a listagem não o mostra
    assert novo["token"] not in client.get("/convites", headers=mundo.h).text
    aceite = client.post(f"/convites/{novo['token']}/aceitar", json={"nome": "Fulano de Tal", "senha": "senha-falsa-longa"})
    assert aceite.status_code == 200, aceite.text
    pr = mundo.db.execute("SELECT prestador_id, papel FROM usuario WHERE lower(email) = %s", (antigo["email"],)).fetchone()
    assert pr == (mundo.p1, "admin")


def test_reemitir_pode_ser_repetido_e_so_o_ultimo_link_vale(mundo):
    c1 = _convidar(mundo.h, tomador_id=mundo.t1)
    c2 = _reemitir(mundo.h, c1["id"]).json()
    c3 = _reemitir(mundo.h, c2["id"]).json()
    assert [_vale(c["token"]) for c in (c1, c2, c3)] == [False, False, True]
    pendentes = mundo.db.execute("SELECT count(*) FROM convite WHERE lower(email) = %s AND usado_em IS NULL "
                                 "AND expira_em > now()", (c1["email"],)).fetchone()[0]
    assert pendentes == 1


def test_reemitir_convite_ja_revogado_gera_novo(mundo):
    c1 = _convidar(mundo.h, tomador_id=mundo.t1)
    assert client.delete(f"/convites/{c1['id']}", headers=mundo.h).status_code == 204
    r = _reemitir(mundo.h, c1["id"])
    assert r.status_code == 201 and _vale(r.json()["token"])


def test_admin_do_tomador_reemite_o_proprio_convite_de_prestador(mundo):
    h = _h_id(mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t1))
    antigo = _convidar(h, nivel="prestador", papel="admin", prestador_id=mundo.p1)
    r = _reemitir(h, antigo["id"])
    assert r.status_code == 201, r.text
    assert not _vale(antigo["token"]) and _vale(r.json()["token"])
    # herda quem convidou: continua na lista do admin
    assert _estado(h, r.json()["id"]) == "pendente"
    criadores = mundo.db.execute("SELECT count(DISTINCT criado_por) FROM convite WHERE id = ANY(%s)",
                                 ([antigo["id"], r.json()["id"]],)).fetchone()[0]
    assert criadores == 1


def test_reemitir_checa_a_permissao_de_convidar_e_nao_revoga_se_recusar(mundo):
    h = _h_id(mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t1))
    antigo = _convidar(h, nivel="prestador", papel="admin", prestador_id=mundo.p1)
    mundo.db.execute("UPDATE contrato SET ativo = false WHERE id = %s", (mundo.c1,))  # o tomador perde o direito
    r = _reemitir(h, antigo["id"])
    assert r.status_code == 403 and "token" not in r.json()
    assert _vale(antigo["token"]) and _estado(mundo.h, antigo["id"]) == "pendente"  # nada foi revogado


def test_reemitir_fora_do_escopo_da_404_igual_a_inexistente(mundo):
    admin1 = _h_id(mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t1))
    admin2 = _h_id(mundo.usuario(nivel="tomador", papel="admin", tomador_id=mundo.t2))
    da_plataforma = _convidar(mundo.h, tomador_id=mundo.t1)
    do_outro = _convidar(admin2, tomador_id=mundo.t2)
    esperado = _reemitir(admin1, INEXISTENTE)
    assert esperado.status_code == 404
    for alheio in (da_plataforma, do_outro):
        r = _reemitir(admin1, alheio["id"])
        assert r.status_code == 404 and r.json() == esperado.json()
        assert _vale(alheio["token"]) and _estado(mundo.h, alheio["id"]) == "pendente"
    assert _reemitir(mundo.h, INEXISTENTE).status_code == 404


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_membro_nao_reemite_403_e_sem_token_401(mundo, nivel):
    vinculo = {"tomador_id": mundo.t1} if nivel == "tomador" else {"prestador_id": mundo.p1}
    convite = _convidar(mundo.h, nivel=nivel, **vinculo)
    h = _h_id(mundo.usuario(nivel=nivel, papel="membro", **vinculo))
    assert _reemitir(h, convite["id"]).status_code == 403
    assert client.post(f"/convites/{convite['id']}/reemitir").status_code == 401
    assert _vale(convite["token"])


def test_reemitir_convite_usado_da_409(mundo):
    convite = _convidar(mundo.h, tomador_id=mundo.t1)
    assert client.post(f"/convites/{convite['token']}/aceitar",
                       json={"nome": "Fulano de Tal", "senha": "senha-falsa-longa"}).status_code == 200
    assert _reemitir(mundo.h, convite["id"]).status_code == 409


def test_reemitir_falhando_na_criacao_preserva_o_convite_antigo(mundo):
    convite = _convidar(mundo.h, tomador_id=mundo.t1)
    mundo.db.execute("UPDATE tomador SET ativo = false WHERE id = %s", (mundo.t1,))
    assert _reemitir(mundo.h, convite["id"]).status_code == 404  # organização desativada
    mundo.db.execute("UPDATE tomador SET ativo = true WHERE id = %s", (mundo.t1,))
    assert _vale(convite["token"])  # a transação voltou: o link antigo segue valendo
