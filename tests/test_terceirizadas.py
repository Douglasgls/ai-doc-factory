"""Cadastro de terceirizadas pelo cliente, convites por organização, GET /usuarios, GET /convites com escopo e
`acesso_prestador` em GET /contratos. Contra o Postgres real; só valores falsos. O banco é compartilhado: cada teste usa
CNPJs, e-mails e organizações próprios e apaga o que criou. O token só aparece em variáveis locais, nunca em mensagem
de asserção."""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import jwt
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.escopo import pode_convidar
from app.routers.auth.actions import UsuarioContexto
from conftest import cnpj_valido

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

SENHA = "senha-falsa-da-terceirizada"
JA_TEM_ACESSO = "prestador já tem acesso; peça ao administrador dele para convidar"


def _email() -> str:
    return f"terc-{uuid.uuid4().hex}@exemplo.invalid"


def _h_id(uid: int) -> dict:
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": str(uid), "iat": agora - 5, "exp": agora + 600}, config.AUTH_SEGREDO, algorithm="HS256")}


class Mundo:
    pass


@pytest.fixture
def mundo():
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    m = Mundo()
    m.db, m.emails, m.tomadores, m.prestadores, m.cnpjs = conn, [], [], [], []

    def tomador():
        i = conn.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id", (f"Tomador {uuid.uuid4().hex}",)
                         ).fetchone()[0]
        m.tomadores.append(i)
        return i
    m.tomador = tomador

    def cnpj():
        c = cnpj_valido(uuid.uuid4().int)
        m.cnpjs.append(c)
        return c
    m.cnpj = cnpj

    def prestador(ativo=True):
        c = cnpj()
        i = conn.execute("INSERT INTO prestador (cnpj, razao_social, ativo) VALUES (%s, %s, %s) RETURNING id",
                         (c, f"Prestador {uuid.uuid4().hex}", ativo)).fetchone()[0]
        m.prestadores.append(i)
        return i
    m.prestador = prestador

    def contrato(tomador_id, prestador_id, ativo=True):
        return conn.execute("INSERT INTO contrato (tomador_id, prestador_id, ativo) VALUES (%s, %s, %s) RETURNING id",
                            (tomador_id, prestador_id, ativo)).fetchone()[0]
    m.contrato = contrato

    def usuario(nivel="plataforma", papel="admin", tomador_id=None, prestador_id=None, ativo=True):
        email = _email()
        m.emails.append(email)
        return conn.execute(
            "INSERT INTO usuario (email, nome, senha_hash, nivel, papel, tomador_id, prestador_id, ativo) "
            "VALUES (%s, 'Pessoa de Teste', 'x', %s, %s, %s, %s, %s) RETURNING id",
            (email, nivel, papel, tomador_id, prestador_id, ativo)).fetchone()[0]
    m.usuario = usuario

    def contexto(uid):
        l = conn.execute("SELECT id, email, nome, nivel, papel, tomador_id, prestador_id FROM usuario WHERE id = %s",
                         (uid,)).fetchone()
        return UsuarioContexto(*l)
    m.contexto = contexto

    def terceirizada(headers, cnpj_=None, razao="Terceirizada Ltda", email=None, **extra):
        email = email or _email()
        m.emails.append(email)
        c = cnpj() if cnpj_ is None else cnpj_
        return client.post("/terceirizadas", headers=headers, json={"cnpj": c, "razao_social": razao, "email": email,
                                                                    **extra})
    m.terceirizada = terceirizada

    def convidar(headers, email=None, **corpo):
        email = email or _email()
        m.emails.append(email)
        return client.post("/convites", headers=headers, json={"email": email, **corpo})
    m.convidar = convidar

    def admin_tomador():
        t = tomador()
        return t, usuario("tomador", "admin", tomador_id=t)
    m.admin_tomador = admin_tomador

    try:
        yield m
    finally:
        # Prestadores criados pela API são achados pelo CNPJ.
        achados = [l[0] for l in conn.execute("SELECT id FROM prestador WHERE cnpj = ANY(%s)", (m.cnpjs,))]
        prestadores = m.prestadores + achados
        conn.execute("DELETE FROM convite WHERE lower(email) = ANY(%s) OR prestador_id = ANY(%s) "
                     "OR tomador_id = ANY(%s)", ([e.lower() for e in m.emails], prestadores, m.tomadores))
        conn.execute("DELETE FROM usuario WHERE lower(email) = ANY(%s) OR prestador_id = ANY(%s) "
                     "OR tomador_id = ANY(%s)", ([e.lower() for e in m.emails], prestadores, m.tomadores))
        conn.execute("DELETE FROM contrato WHERE tomador_id = ANY(%s) OR prestador_id = ANY(%s)",
                     (m.tomadores, prestadores))
        conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (m.tomadores,))
        conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (prestadores,))
        conn.close()


def _aceitar(token, nome="Fulano de Tal", senha=SENHA):
    return client.post(f"/convites/{token}/aceitar", json={"nome": nome, "senha": senha})


def _contagens(mundo, cnpj):
    pid = mundo.db.execute("SELECT id FROM prestador WHERE cnpj = %s", (cnpj,)).fetchall()
    ids = [l[0] for l in pid]
    return (len(ids),
            mundo.db.execute("SELECT count(*) FROM contrato WHERE prestador_id = ANY(%s)", (ids,)).fetchone()[0],
            mundo.db.execute("SELECT count(*) FROM convite WHERE prestador_id = ANY(%s)", (ids,)).fetchone()[0])


# ---------- matriz de pode_convidar, via POST /convites ----------

def test_plataforma_convida_qualquer_nivel_e_papel(mundo):
    h = _h_id(mundo.usuario())
    t, p = mundo.tomador(), mundo.prestador()
    mundo.contrato(t, p)
    mundo.usuario("prestador", "admin", prestador_id=p)  # plataforma ignora a regra do prestador com usuário
    for corpo in ({"nivel": "plataforma", "papel": "membro"}, {"nivel": "tomador", "papel": "membro", "tomador_id": t},
                  {"nivel": "prestador", "papel": "admin", "prestador_id": p}):
        assert mundo.convidar(h, **corpo).status_code == 201


@pytest.mark.parametrize("papel", ["admin", "membro"])
def test_admin_do_tomador_convida_colega_so_do_proprio_tomador(mundo, papel):
    t, uid = mundo.admin_tomador()
    h = _h_id(uid)
    assert mundo.convidar(h, nivel="tomador", papel=papel, tomador_id=t).status_code == 201
    assert mundo.convidar(h, nivel="tomador", papel=papel, tomador_id=mundo.tomador()).status_code == 403


def test_admin_do_tomador_nao_convida_plataforma(mundo):
    _, uid = mundo.admin_tomador()
    for papel in ("admin", "membro"):
        assert mundo.convidar(_h_id(uid), nivel="plataforma", papel=papel).status_code == 403


def test_admin_do_tomador_convida_admin_de_prestador_com_contrato_ativo_sem_usuarios(mundo):
    t, uid = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(t, p)
    r = mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=p)
    assert r.status_code == 201 and r.json()["token"]


def test_admin_do_tomador_so_convida_prestador_como_admin(mundo):
    t, uid = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(t, p)
    assert mundo.convidar(_h_id(uid), nivel="prestador", papel="membro", prestador_id=p).status_code == 403


def test_admin_do_tomador_nao_convida_prestador_sem_contrato_ou_com_contrato_inativo(mundo):
    t, uid = mundo.admin_tomador()
    sem_contrato, inativo, prestador_off = mundo.prestador(), mundo.prestador(), mundo.prestador()
    mundo.contrato(t, inativo, ativo=False)
    mundo.contrato(t, prestador_off)
    mundo.db.execute("UPDATE prestador SET ativo = false WHERE id = %s", (prestador_off,))
    for p in (sem_contrato, inativo, prestador_off):
        r = mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=p)
        assert r.status_code == 403, p
        assert "token" not in r.json()


def test_prestador_com_usuario_ativo_barra_o_tomador_com_mensagem(mundo):
    t, uid = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(t, p)
    mundo.usuario("prestador", "membro", prestador_id=p)
    r = mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=p)
    assert r.status_code == 403 and r.json()["detail"] == JA_TEM_ACESSO


def test_usuario_inativo_do_prestador_nao_conta_como_acesso(mundo):
    t, uid = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(t, p)
    mundo.usuario("prestador", "admin", prestador_id=p, ativo=False)
    assert mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=p).status_code == 201


def test_cliente_b_nao_convida_para_prestador_que_ja_tem_usuarios_por_causa_do_cliente_a(mundo):
    """O cenário de segurança: B poria alguém dentro do prestador e essa pessoa veria o contrato dele com A."""
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    ra = mundo.terceirizada(_h_id(ua), cnpj_=cnpj)
    assert ra.status_code == 201 and ra.json()["acesso"] == "convite_criado"
    assert _aceitar(ra.json()["convite"]["token"]).status_code == 200  # o prestador ganha o primeiro usuário
    rb = mundo.terceirizada(_h_id(ub), cnpj_=cnpj)
    assert rb.status_code == 201 and rb.json()["acesso"] == "ja_tem_acesso"
    p = rb.json()["prestador"]["id"]
    for corpo in ({"papel": "admin"}, {"papel": "membro"}):
        r = mundo.convidar(_h_id(ub), nivel="prestador", prestador_id=p, **corpo)
        assert r.status_code == 403 and "token" not in r.json()
    # nem o cliente A, que cadastrou primeiro, convida depois que o prestador tem alguém
    assert mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).status_code == 403
    assert mundo.db.execute("SELECT count(*) FROM convite WHERE prestador_id = %s AND usado_em IS NULL",
                            (p,)).fetchone()[0] == 0


def test_convite_pendente_de_outra_organizacao_barra_o_tomador_mas_o_proprio_nao(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(ta, p)
    mundo.contrato(tb, p)
    assert mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).status_code == 201
    r = mundo.convidar(_h_id(ub), nivel="prestador", papel="admin", prestador_id=p)
    assert r.status_code == 403 and "token" not in r.json()
    # reenviar para outro e-mail, pelo mesmo tomador que convidou, continua possível
    assert mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).status_code == 201


def test_membro_do_tomador_nao_convida_ninguem(mundo):
    t = mundo.tomador()
    p = mundo.prestador()
    mundo.contrato(t, p)
    h = _h_id(mundo.usuario("tomador", "membro", tomador_id=t))
    for corpo in ({"nivel": "tomador", "papel": "membro", "tomador_id": t},
                  {"nivel": "prestador", "papel": "admin", "prestador_id": p}):
        assert mundo.convidar(h, **corpo).status_code == 403


@pytest.mark.parametrize("papel", ["admin", "membro"])
def test_admin_do_prestador_convida_colega_so_do_proprio_prestador(mundo, papel):
    p, outro = mundo.prestador(), mundo.prestador()
    h = _h_id(mundo.usuario("prestador", "admin", prestador_id=p))
    assert mundo.convidar(h, nivel="prestador", papel=papel, prestador_id=p).status_code == 201
    assert mundo.convidar(h, nivel="prestador", papel=papel, prestador_id=outro).status_code == 403


def test_admin_do_prestador_nao_convida_tomador_nem_plataforma(mundo):
    p, t = mundo.prestador(), mundo.tomador()
    h = _h_id(mundo.usuario("prestador", "admin", prestador_id=p))
    assert mundo.convidar(h, nivel="tomador", papel="membro", tomador_id=t).status_code == 403
    assert mundo.convidar(h, nivel="plataforma", papel="membro").status_code == 403


def test_membro_do_prestador_nao_convida(mundo):
    p = mundo.prestador()
    h = _h_id(mundo.usuario("prestador", "membro", prestador_id=p))
    assert mundo.convidar(h, nivel="prestador", papel="membro", prestador_id=p).status_code == 403


def test_pode_convidar_matriz_direta(mundo, sessao):
    """A função de decisão, chamada direto (com sessão), sem passar pelo HTTP."""
    t, p = mundo.tomador(), mundo.prestador()
    mundo.contrato(t, p)
    plat = mundo.contexto(mundo.usuario())
    adm_t = mundo.contexto(mundo.usuario("tomador", "admin", tomador_id=t))
    mem_t = mundo.contexto(mundo.usuario("tomador", "membro", tomador_id=t))
    adm_p = mundo.contexto(mundo.usuario("prestador", "admin", prestador_id=p))
    mem_p = mundo.contexto(mundo.usuario("prestador", "membro", prestador_id=p))
    c = sessao
    assert pode_convidar(c, plat, "plataforma", "admin", None, None)
    assert pode_convidar(c, plat, "tomador", "membro", t, None)
    assert pode_convidar(c, adm_t, "tomador", "membro", t, None)
    assert not pode_convidar(c, adm_t, "tomador", "membro", t + 10 ** 6, None)
    assert not pode_convidar(c, adm_t, "plataforma", "admin", None, None)
    assert not pode_convidar(c, adm_t, "prestador", "admin", None, p)  # o prestador já tem usuário (adm_p)
    assert pode_convidar(c, adm_p, "prestador", "membro", None, p)
    assert not pode_convidar(c, adm_p, "tomador", "membro", t, None)
    assert not pode_convidar(c, mem_t, "tomador", "membro", t, None)
    assert not pode_convidar(c, mem_p, "prestador", "membro", None, p)


# ---------- POST /terceirizadas ----------

def test_cadastro_de_cnpj_novo_cria_prestador_contrato_ativo_e_convite(mundo):
    t, uid = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    email = _email()
    r = mundo.terceirizada(_h_id(uid), cnpj_=cnpj, razao="  Nova Terceirizada Ltda ", email=email.upper())
    assert r.status_code == 201, r.text
    corpo = r.json()
    assert set(corpo) == {"contrato", "prestador", "acesso", "convite"}
    assert corpo["acesso"] == "convite_criado" and corpo["contrato"]["ativo"] is True
    assert corpo["prestador"]["cnpj"] == cnpj and corpo["prestador"]["razao_social"] == "Nova Terceirizada Ltda"
    assert set(corpo["convite"]) == {"id", "email", "expira_em", "token"}
    assert corpo["convite"]["email"] == email.lower() and len(corpo["convite"]["token"]) >= 43
    assert _contagens(mundo, cnpj) == (1, 1, 1)
    linha = mundo.db.execute("SELECT nivel, papel, prestador_id, tomador_id, criado_por FROM convite WHERE id = %s",
                             (corpo["convite"]["id"],)).fetchone()
    assert linha == ("prestador", "admin", corpo["prestador"]["id"], None, uid)
    c = mundo.db.execute("SELECT tomador_id, prestador_id, ativo FROM contrato WHERE id = %s",
                         (corpo["contrato"]["id"],)).fetchone()
    assert c == (t, corpo["prestador"]["id"], True)


def test_cnpj_com_pontuacao_e_normalizado_e_invalido_da_422(mundo):
    _, uid = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    pontuado = f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    r = mundo.terceirizada(_h_id(uid), cnpj_=pontuado)
    assert r.status_code == 201 and r.json()["prestador"]["cnpj"] == cnpj
    for invalido in ("11222333000180", "123", "abcdefghijklmn", ""):
        assert mundo.terceirizada(_h_id(uid), cnpj_=invalido).status_code == 422
    assert mundo.terceirizada(_h_id(uid), email="sem-arroba").status_code == 422
    assert mundo.terceirizada(_h_id(uid), razao="   ").status_code == 422


def test_cnpj_existente_reutiliza_o_prestador_sem_trocar_a_razao_social(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    ra = mundo.terceirizada(_h_id(ua), cnpj_=cnpj, razao="Razão Original Ltda")
    rb = mundo.terceirizada(_h_id(ub), cnpj_=cnpj, razao="Razão Trocada pelo Cliente B")
    assert ra.status_code == rb.status_code == 201
    assert rb.json()["prestador"]["id"] == ra.json()["prestador"]["id"]
    assert rb.json()["prestador"]["razao_social"] == "Razão Original Ltda"
    assert mundo.db.execute("SELECT razao_social FROM prestador WHERE cnpj = %s", (cnpj,)).fetchone()[0] \
        == "Razão Original Ltda"
    assert rb.json()["contrato"]["id"] != ra.json()["contrato"]["id"]
    assert _contagens(mundo, cnpj) == (1, 2, 1)


def test_prestador_com_usuarios_nao_recebe_convite_novo(mundo):
    t, uid = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.usuario("prestador", "admin", prestador_id=p)
    cnpj = mundo.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (p,)).fetchone()[0]
    r = mundo.terceirizada(_h_id(uid), cnpj_=cnpj)
    assert r.status_code == 201
    assert r.json()["acesso"] == "ja_tem_acesso" and r.json()["convite"] is None
    assert _contagens(mundo, cnpj) == (1, 1, 0)


def test_convite_pendente_nao_gera_token_novo(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    assert mundo.terceirizada(_h_id(ua), cnpj_=cnpj).json()["acesso"] == "convite_criado"
    rb = mundo.terceirizada(_h_id(ub), cnpj_=cnpj)
    assert rb.status_code == 201 and rb.json()["acesso"] == "convite_pendente" and rb.json()["convite"] is None
    assert "token" not in rb.text
    assert _contagens(mundo, cnpj) == (1, 2, 1)


def test_convite_expirado_deixa_de_ser_pendente_e_gera_outro(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    ra = mundo.terceirizada(_h_id(ua), cnpj_=cnpj)
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 minute' WHERE id = %s",
                     (ra.json()["convite"]["id"],))
    rb = mundo.terceirizada(_h_id(ub), cnpj_=cnpj)
    assert rb.json()["acesso"] == "convite_criado" and rb.json()["convite"]["token"]


def test_contrato_duplicado_da_409_e_nao_cria_convite(mundo):
    t, uid = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    assert mundo.terceirizada(_h_id(uid), cnpj_=cnpj).status_code == 201
    r = mundo.terceirizada(_h_id(uid), cnpj_=cnpj)
    assert r.status_code == 409 and "já cadastrada" in r.json()["detail"]
    assert _contagens(mundo, cnpj) == (1, 1, 1)


def test_prestador_inativo_da_409(mundo):
    _, uid = mundo.admin_tomador()
    p = mundo.prestador(ativo=False)
    cnpj = mundo.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (p,)).fetchone()[0]
    assert mundo.terceirizada(_h_id(uid), cnpj_=cnpj).status_code == 409
    assert _contagens(mundo, cnpj) == (1, 0, 0)


def test_email_ja_usado_da_409_e_desfaz_tudo(mundo):
    _, uid = mundo.admin_tomador()
    existente = mundo.db.execute("SELECT email FROM usuario WHERE id = %s", (mundo.usuario(),)).fetchone()[0]
    cnpj = mundo.cnpj()
    assert mundo.terceirizada(_h_id(uid), cnpj_=cnpj, email=existente).status_code == 409
    assert _contagens(mundo, cnpj) == (0, 0, 0)  # nem prestador nem contrato ficaram


def test_so_admin_do_tomador_e_plataforma_cadastram(mundo):
    t = mundo.tomador()
    p = mundo.prestador()
    for nivel, papel, vinculo in (("tomador", "membro", {"tomador_id": t}), ("prestador", "admin", {"prestador_id": p}),
                                  ("prestador", "membro", {"prestador_id": p})):
        cnpj = mundo.cnpj()
        h = _h_id(mundo.usuario(nivel, papel, **vinculo))
        r = mundo.terceirizada(h, cnpj_=cnpj)
        assert r.status_code == 403, (nivel, papel)
        assert _contagens(mundo, cnpj) == (0, 0, 0)
    assert client.post("/terceirizadas", json={"cnpj": mundo.cnpj(), "razao_social": "X", "email": _email()}
                       ).status_code == 401


def test_admin_do_tomador_nao_cadastra_em_nome_de_outro_tomador(mundo):
    t, uid = mundo.admin_tomador()
    outro = mundo.tomador()
    assert mundo.terceirizada(_h_id(uid), tomador_id=outro).status_code == 403
    assert mundo.terceirizada(_h_id(uid), tomador_id=t).status_code == 201  # o próprio id é aceito


def test_plataforma_cadastra_informando_o_tomador(mundo):
    h = _h_id(mundo.usuario())
    t = mundo.tomador()
    assert mundo.terceirizada(h).status_code == 422  # sem tomador_id
    assert mundo.terceirizada(h, tomador_id=2 ** 62).status_code == 404
    r = mundo.terceirizada(h, tomador_id=t)
    assert r.status_code == 201
    assert mundo.db.execute("SELECT tomador_id FROM contrato WHERE id = %s", (r.json()["contrato"]["id"],)
                            ).fetchone()[0] == t


def test_tomador_desativado_nao_cadastra(mundo):
    t, uid = mundo.admin_tomador()
    h = _h_id(uid)
    mundo.db.execute("UPDATE tomador SET ativo = false WHERE id = %s", (t,))
    assert mundo.terceirizada(h).status_code == 401  # a autenticação já recusa usuário de organização inativa


# ---------- corridas ----------

def test_corrida_mesmo_tomador_e_mesmo_cnpj_cria_um_prestador_um_contrato_um_convite(mundo):
    t, uid = mundo.admin_tomador()
    h = _h_id(uid)
    cnpj = mundo.cnpj()
    with ThreadPoolExecutor(8) as pool:
        codigos = list(pool.map(lambda _: mundo.terceirizada(h, cnpj_=cnpj).status_code, range(8)))
    assert sorted(codigos) == [201] + [409] * 7
    assert _contagens(mundo, cnpj) == (1, 1, 1)


def test_corrida_de_clientes_diferentes_no_mesmo_cnpj(mundo):
    admins = [mundo.admin_tomador() for _ in range(5)]
    cnpj = mundo.cnpj()
    with ThreadPoolExecutor(5) as pool:
        respostas = list(pool.map(lambda a: mundo.terceirizada(_h_id(a[1]), cnpj_=cnpj, razao=f"Razão {a[0]}"),
                                  admins))
    assert [r.status_code for r in respostas] == [201] * 5
    assert len({r.json()["prestador"]["id"] for r in respostas}) == 1
    assert len({r.json()["prestador"]["razao_social"] for r in respostas}) == 1  # todos veem a razão que ficou
    acessos = sorted(r.json()["acesso"] for r in respostas)
    assert acessos == ["convite_criado"] + ["convite_pendente"] * 4
    assert _contagens(mundo, cnpj) == (1, 5, 1)


# ---------- fluxo completo e isolamento ----------

def test_fluxo_cliente_cadastra_prestador_aceita_convida_colega_e_outro_cliente_nao_entra(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    cnpj = mundo.cnpj()
    ra = mundo.terceirizada(_h_id(ua), cnpj_=cnpj, razao="Fluxo Ltda")
    login = _aceitar(ra.json()["convite"]["token"], nome="Admin Fluxo")
    assert login.status_code == 200
    h_prest = {"Authorization": "Bearer " + login.json()["access_token"]}
    p = ra.json()["prestador"]["id"]
    colega = mundo.convidar(h_prest, nivel="prestador", papel="membro", prestador_id=p)
    assert colega.status_code == 201 and _aceitar(colega.json()["token"], nome="Colega Fluxo").status_code == 200
    rb = mundo.terceirizada(_h_id(ub), cnpj_=cnpj, razao="Outra Razão")
    assert rb.json()["acesso"] == "ja_tem_acesso"
    assert mundo.convidar(_h_id(ub), nivel="prestador", papel="admin", prestador_id=p).status_code == 403
    # o admin da terceirizada enxerga os dois contratos; cada cliente, só o seu
    assert sorted(c["tomador_id"] for c in client.get("/contratos", headers=h_prest).json()) == sorted([ta, tb])
    assert [c["tomador_id"] for c in client.get("/contratos", headers=_h_id(ub)).json()] == [tb]
    assert [c["tomador_id"] for c in client.get("/contratos", headers=_h_id(ua)).json()] == [ta]


# ---------- GET /contratos: acesso_prestador ----------

def test_contratos_traz_acesso_prestador(mundo):
    t, uid = mundo.admin_tomador()
    sem, pendente, ativo = mundo.prestador(), mundo.prestador(), mundo.prestador()
    contratos = {p: mundo.contrato(t, p) for p in (sem, pendente, ativo)}
    mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=pendente)
    mundo.usuario("prestador", "admin", prestador_id=ativo)
    # usuário inativo + convite expirado não contam
    outro = mundo.prestador()
    contratos[outro] = mundo.contrato(t, outro)
    mundo.usuario("prestador", "admin", prestador_id=outro, ativo=False)
    por_id = {c["id"]: c["acesso_prestador"] for c in client.get("/contratos", headers=_h_id(uid)).json()}
    assert por_id[contratos[sem]] == "sem_acesso" and por_id[contratos[outro]] == "sem_acesso"
    assert por_id[contratos[pendente]] == "convite_pendente" and por_id[contratos[ativo]] == "ativo"
    mundo.db.execute("UPDATE convite SET expira_em = now() - interval '1 minute' WHERE prestador_id = %s", (pendente,))
    por_id = {c["id"]: c["acesso_prestador"] for c in client.get("/contratos", headers=_h_id(uid)).json()}
    assert por_id[contratos[pendente]] == "sem_acesso"
    # e o reenvio (POST /convites) só passa onde não há usuário
    assert mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=pendente).status_code == 201
    assert mundo.convidar(_h_id(uid), nivel="prestador", papel="admin", prestador_id=ativo).status_code == 403


# ---------- GET /convites e GET /usuarios com escopo ----------

def test_get_convites_por_organizacao(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(ta, p)
    up = mundo.usuario("prestador", "admin", prestador_id=p)
    plat = mundo.usuario()
    c_a = mundo.convidar(_h_id(ua), nivel="tomador", papel="membro", tomador_id=ta).json()["id"]
    c_b = mundo.convidar(_h_id(ub), nivel="tomador", papel="membro", tomador_id=tb).json()["id"]
    c_p = mundo.convidar(_h_id(up), nivel="prestador", papel="membro", prestador_id=p).json()["id"]
    c_plat = mundo.convidar(_h_id(plat), nivel="plataforma", papel="membro").json()["id"]

    def ids(uid):
        r = client.get("/convites", headers=_h_id(uid))
        assert r.status_code == 200
        assert not any("token" in c for c in r.json())
        return {c["id"] for c in r.json()}
    assert ids(ua) & {c_a, c_b, c_p, c_plat} == {c_a}
    assert ids(ub) & {c_a, c_b, c_p, c_plat} == {c_b}
    assert ids(up) & {c_a, c_b, c_p, c_plat} == {c_p}
    assert {c_a, c_b, c_p, c_plat} <= ids(plat)
    for membro in (mundo.usuario("tomador", "membro", tomador_id=ta),
                   mundo.usuario("prestador", "membro", prestador_id=p)):
        assert client.get("/convites", headers=_h_id(membro)).status_code == 403


def test_convite_do_cliente_ao_prestador_aparece_para_o_cliente_e_nao_para_o_prestador(mundo):
    t, uid = mundo.admin_tomador()
    r = mundo.terceirizada(_h_id(uid))
    p = r.json()["prestador"]["id"]
    visto = {c["id"] for c in client.get("/convites", headers=_h_id(uid)).json()}
    assert r.json()["convite"]["id"] in visto
    admin_p = mundo.usuario("prestador", "admin", prestador_id=p)
    assert r.json()["convite"]["id"] not in {c["id"] for c in client.get("/convites", headers=_h_id(admin_p)).json()}


def test_get_usuarios_por_organizacao(mundo):
    ta, ua = mundo.admin_tomador()
    tb, ub = mundo.admin_tomador()
    p = mundo.prestador()
    up = mundo.usuario("prestador", "admin", prestador_id=p)
    inativo = mundo.usuario("tomador", "membro", tomador_id=ta, ativo=False)
    plat = mundo.usuario()

    def lista(uid):
        r = client.get("/usuarios", headers=_h_id(uid))
        assert r.status_code == 200
        assert "senha" not in r.text
        for u in r.json():
            assert set(u) == {"id", "nome", "email", "nivel", "papel", "ativo", "criado_em"}
        return r.json()
    da = lista(ua)
    assert {u["id"] for u in da} == {ua, inativo}
    assert next(u for u in da if u["id"] == inativo)["ativo"] is False
    assert {u["id"] for u in lista(ub)} == {ub}
    assert {u["id"] for u in lista(up)} == {up}
    tudo = {u["id"] for u in lista(plat)}
    assert {ua, ub, up, inativo, plat} <= tudo
    for membro in (mundo.usuario("tomador", "membro", tomador_id=ta),
                   mundo.usuario("prestador", "membro", prestador_id=p)):
        assert client.get("/usuarios", headers=_h_id(membro)).status_code == 403
    assert client.get("/usuarios").status_code == 401


def test_segundo_convite_do_cliente_nao_entra_depois_que_o_prestador_ja_tem_alguem(mundo):
    """O cliente A cria dois convites de admin enquanto o prestador não tem ninguém. Aceito o primeiro, o segundo não
    pode mais entrar: a pessoa veria os contratos do prestador com outros clientes (aqui, o cliente B)."""
    ta, ua = mundo.admin_tomador()
    tb, _ = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(ta, p)
    primeiro = mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).json()
    segundo = mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).json()
    assert _aceitar(primeiro["token"]).status_code == 200
    mundo.contrato(tb, p)
    r = _aceitar(segundo["token"])
    assert r.status_code == 404 and r.json() == {"detail": "convite inválido, usado ou expirado"}
    assert mundo.db.execute("SELECT count(*) FROM usuario WHERE prestador_id = %s", (p,)).fetchone()[0] == 1


def test_admin_do_prestador_continua_convidando_colegas_depois_do_primeiro_acesso(mundo):
    """A recusa acima vale só para convite criado por cliente; o do próprio prestador entra normalmente."""
    ta, ua = mundo.admin_tomador()
    p = mundo.prestador()
    mundo.contrato(ta, p)
    assert _aceitar(mundo.convidar(_h_id(ua), nivel="prestador", papel="admin", prestador_id=p).json()["token"]
                    ).status_code == 200
    admin_p = mundo.db.execute("SELECT id FROM usuario WHERE prestador_id = %s", (p,)).fetchone()[0]
    colega = mundo.convidar(_h_id(admin_p), nivel="prestador", papel="membro", prestador_id=p).json()
    assert _aceitar(colega["token"]).status_code == 200
