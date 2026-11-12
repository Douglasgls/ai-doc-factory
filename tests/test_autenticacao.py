"""Autenticação por usuário (tabela `usuario`): login, JWT, releitura no banco, falha fechada e varredura de
rotas. Sem rede; só valores falsos de teste. Cada teste remove o que criou."""
import re
from datetime import datetime, timedelta, timezone

import jwt
import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import config, senhas
from app.api import app

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

EMAIL, SENHA = "pessoa-teste@exemplo.invalid", "senha-falsa-teste"
CNPJ_PRESTADOR, NOME_TOMADOR = "11222333000181", "Tomador de Teste Auth"


@pytest.fixture(scope="module")
def hash_senha():
    return senhas.gerar_hash(SENHA)


@pytest.fixture
def banco(hash_senha):
    """Conexão autocommit + criadores que lembram o que inseriram e apagam tudo no fim (usuários antes das organizações)."""
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    criados = {"usuario": [], "tomador": [], "prestador": []}

    class Ajuda:
        db = conn

        @staticmethod
        def tomador(ativo=True):
            i = conn.execute("INSERT INTO tomador (nome, ativo) VALUES (%s, %s) RETURNING id",
                             (NOME_TOMADOR, ativo)).fetchone()[0]
            criados["tomador"].append(i)
            return i

        @staticmethod
        def prestador(ativo=True):
            i = conn.execute("INSERT INTO prestador (cnpj, razao_social, ativo) VALUES (%s, 'Prestador de Teste', %s) "
                             "RETURNING id", (CNPJ_PRESTADOR, ativo)).fetchone()[0]
            criados["prestador"].append(i)
            return i

        @staticmethod
        def usuario(email=EMAIL, nivel="plataforma", papel="admin", tomador_id=None, prestador_id=None, ativo=True,
                    senha_hash="padrao"):
            if senha_hash == "padrao":
                senha_hash = hash_senha
            i = conn.execute(
                "INSERT INTO usuario (email, nome, senha_hash, nivel, papel, tomador_id, prestador_id, ativo) "
                "VALUES (%s, 'Pessoa de Teste', %s, %s, %s, %s, %s, %s) RETURNING id",
                (email, senha_hash, nivel, papel, tomador_id, prestador_id, ativo)).fetchone()[0]
            criados["usuario"].append(i)
            return i

    try:
        yield Ajuda
    finally:
        conn.execute("DELETE FROM usuario WHERE id = ANY(%s)", (criados["usuario"],))
        conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (criados["tomador"],))
        conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (criados["prestador"],))
        conn.close()


def _login(email=EMAIL, senha=SENHA):
    return client.post("/auth/login", json={"usuario": email, "senha": senha})


def _token(email=EMAIL):
    r = _login(email)
    assert r.status_code == 200
    return r.json()["access_token"]


def _com(token):
    return {"Authorization": f"Bearer {token}"}


def _jwt(sub, **extra):
    agora = datetime.now(timezone.utc)
    claims = {"sub": str(sub), "iat": int(agora.timestamp()), "exp": int((agora + timedelta(minutes=5)).timestamp())}
    claims.update(extra)
    return jwt.encode(claims, config.AUTH_SEGREDO, algorithm="HS256")


# ---------- login ----------

def test_login_certo_devolve_token_com_claims(banco):
    uid = banco.usuario()
    r = _login()
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["token_type"] == "bearer" and corpo["expira_em"]
    claims = jwt.decode(corpo["access_token"], config.AUTH_SEGREDO, algorithms=["HS256"])
    assert claims["sub"] == str(uid)
    assert (claims["nivel"], claims["papel"], claims["tomador_id"], claims["prestador_id"]) == \
        ("plataforma", "admin", None, None)
    assert claims["exp"] - claims["iat"] == config.AUTH_EXPIRA_MIN * 60


def test_token_do_login_acessa_me_e_rota_de_dados(banco):
    uid = banco.usuario()
    token = _token()
    me = client.get("/auth/me", headers=_com(token))
    assert me.status_code == 200
    assert me.json() == {"id": uid, "email": EMAIL, "nome": "Pessoa de Teste", "nivel": "plataforma",
                         "papel": "admin", "tomador_id": None, "prestador_id": None, "usuario": EMAIL}
    assert client.get("/tipos", headers=_com(token)).status_code == 200


@pytest.mark.parametrize("digitado", ["PESSOA-TESTE@EXEMPLO.INVALID", "  pessoa-teste@exemplo.invalid  ",
                                      "Pessoa-Teste@Exemplo.Invalid\t"])
def test_email_com_caixa_e_espacos_diferentes(banco, digitado):
    banco.usuario()
    assert _login(digitado).status_code == 200


def test_email_gravado_com_maiusculas_entra_com_minusculas(banco):
    banco.usuario(email="Pessoa-Teste@Exemplo.Invalid")
    assert _login("pessoa-teste@exemplo.invalid").status_code == 200


def test_senha_errada(banco):
    banco.usuario()
    assert _login(senha="errada").status_code == 401


def test_usuario_inexistente_e_senha_errada_dao_resposta_identica(banco):
    banco.usuario()
    inexistente = _login("ninguem@exemplo.invalid")
    errada = _login(senha="errada")
    assert inexistente.status_code == errada.status_code == 401
    assert inexistente.json() == errada.json() == {"detail": "usuário ou senha inválidos"}
    assert inexistente.headers["www-authenticate"] == errada.headers["www-authenticate"] == "Bearer"


def test_usuario_inexistente_tambem_roda_verificacao_de_hash(monkeypatch):
    chamadas = []
    real = senhas.verificar
    monkeypatch.setattr(senhas, "verificar", lambda s, h: chamadas.append(h) or real(s, h))
    assert _login("ninguem@exemplo.invalid").status_code == 401
    assert len(chamadas) == 1 and senhas._ler(chamadas[0]) is not None  # hash fictício válido, com custo atual


def test_usuario_inativo(banco):
    banco.usuario(ativo=False)
    r = _login()
    assert r.status_code == 401 and r.json() == {"detail": "usuário ou senha inválidos"}


def test_usuario_sem_senha_convidado(banco):
    banco.usuario(senha_hash=None)
    assert _login().status_code == 401
    assert _login(senha="").status_code == 401


def test_organizacao_inativa_bloqueia_tomador_e_prestador(banco):
    banco.usuario(email="t@exemplo.invalid", nivel="tomador", papel="membro", tomador_id=banco.tomador(ativo=False))
    banco.usuario(email="p@exemplo.invalid", nivel="prestador", papel="membro",
                  prestador_id=banco.prestador(ativo=False))
    assert _login("t@exemplo.invalid").status_code == 401
    assert _login("p@exemplo.invalid").status_code == 401


def test_organizacao_ativa_permite_login(banco):
    banco.usuario(email="t@exemplo.invalid", nivel="tomador", papel="membro", tomador_id=banco.tomador())
    assert _login("t@exemplo.invalid").status_code == 200


def test_senha_gigante_e_recusada_sem_erro(banco):
    banco.usuario()
    assert _login(senha="a" * 100_000).status_code == 401


def test_login_com_caracteres_nao_ascii_nao_quebra(banco):
    assert _login("usuário-ç@exemplo.invalid", "sênha-ã").status_code == 401


def test_senha_nao_vai_para_o_log(banco, caplog):
    banco.usuario()
    with caplog.at_level("DEBUG"):
        _login(senha="senha-errada-xyz")
    assert "senha-errada-xyz" not in caplog.text


def test_rehash_automatico_de_hash_com_parametros_mais_fracos(banco):
    fraco = senhas.gerar_hash(SENHA, n=2 ** 10, r=8, p=1)
    uid = banco.usuario(senha_hash=fraco)
    assert _login().status_code == 200
    novo = banco.db.execute("SELECT senha_hash FROM usuario WHERE id = %s", (uid,)).fetchone()[0]
    assert novo != fraco and not senhas.precisa_rehash(novo) and senhas.verificar(SENHA, novo)
    assert _login().status_code == 200  # continua entrando com o hash novo


def test_senha_errada_nao_regrava_hash(banco):
    fraco = senhas.gerar_hash(SENHA, n=2 ** 10, r=8, p=1)
    uid = banco.usuario(senha_hash=fraco)
    assert _login(senha="errada").status_code == 401
    assert banco.db.execute("SELECT senha_hash FROM usuario WHERE id = %s", (uid,)).fetchone()[0] == fraco


# ---------- token ----------

def test_sem_token_responde_401_com_www_authenticate():
    r = client.get("/tipos")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("cabecalho", ["Bearer", "Bearer lixo.sem.sentido", "Basic abc", "Bearer a.b", "token"])
def test_token_malformado(cabecalho):
    assert client.get("/tipos", headers={"Authorization": cabecalho}).status_code == 401


def test_token_expirado(banco):
    uid = banco.usuario()
    passado = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    assert client.get("/auth/me", headers=_com(_jwt(uid, exp=passado))).status_code == 401


def test_token_assinado_com_outro_segredo(banco):
    uid = banco.usuario()
    agora = int(datetime.now(timezone.utc).timestamp())
    falso = jwt.encode({"sub": str(uid), "iat": agora, "exp": agora + 300},
                       "outro-segredo-falso-com-mais-de-32-bytes!", algorithm="HS256")
    assert client.get("/auth/me", headers=_com(falso)).status_code == 401


def test_token_com_alg_none_ou_outro_hmac(banco):
    uid = banco.usuario()
    agora = int(datetime.now(timezone.utc).timestamp())
    claims = {"sub": str(uid), "iat": agora, "exp": agora + 300}
    sem_assinatura = jwt.encode(claims, key=None, algorithm="none")
    hs512 = jwt.encode(claims, config.AUTH_SEGREDO, algorithm="HS512")
    assert client.get("/auth/me", headers=_com(sem_assinatura)).status_code == 401
    assert client.get("/auth/me", headers=_com(hs512)).status_code == 401


def test_token_sem_exp(banco):
    uid = banco.usuario()
    agora = int(datetime.now(timezone.utc).timestamp())
    sem_exp = jwt.encode({"sub": str(uid), "iat": agora}, config.AUTH_SEGREDO, algorithm="HS256")
    assert client.get("/auth/me", headers=_com(sem_exp)).status_code == 401


@pytest.mark.parametrize("sub", ["usuario-teste", "admin", "", "1.5", "-1", "1e3", "٣", "99999999999999999999999"])
def test_token_no_formato_antigo_ou_sub_invalido_da_401_sem_500(banco, sub):
    banco.usuario()
    assert client.get("/auth/me", headers=_com(_jwt(sub))).status_code == 401
    assert client.get("/tipos", headers=_com(_jwt(sub))).status_code == 401


def test_token_de_usuario_inexistente(banco):
    uid = banco.usuario()
    token = _token()
    banco.db.execute("DELETE FROM usuario WHERE id = %s", (uid,))
    assert client.get("/auth/me", headers=_com(token)).status_code == 401


def test_token_na_query_string_nao_vale(banco):
    banco.usuario()
    token = _token()
    assert client.get("/tipos", params={"token": token, "access_token": token}).status_code == 401


def test_usuario_desativado_depois_do_token_perde_acesso_na_requisicao_seguinte(banco):
    uid = banco.usuario()
    token = _token()
    assert client.get("/tipos", headers=_com(token)).status_code == 200
    banco.db.execute("UPDATE usuario SET ativo = false WHERE id = %s", (uid,))
    assert client.get("/tipos", headers=_com(token)).status_code == 401
    assert client.get("/auth/me", headers=_com(token)).status_code == 401


def test_organizacao_desativada_depois_do_token_perde_acesso(banco):
    tid = banco.tomador()
    banco.usuario(nivel="tomador", papel="membro", tomador_id=tid)
    token = _token()
    assert client.get("/auth/me", headers=_com(token)).status_code == 200
    banco.db.execute("UPDATE tomador SET ativo = false WHERE id = %s", (tid,))
    assert client.get("/auth/me", headers=_com(token)).status_code == 401


def test_mudanca_de_papel_no_banco_aparece_em_me_sem_novo_login(banco):
    uid = banco.usuario(papel="admin")
    token = _token()
    assert client.get("/auth/me", headers=_com(token)).json()["papel"] == "admin"
    banco.db.execute("UPDATE usuario SET papel = 'membro' WHERE id = %s", (uid,))
    assert client.get("/auth/me", headers=_com(token)).json()["papel"] == "membro"


def test_nivel_do_banco_vale_mais_que_o_do_token(banco):
    """Token com claims de plataforma, mas o banco diz tomador: vale o banco."""
    uid = banco.usuario(nivel="tomador", papel="membro", tomador_id=banco.tomador())
    forjado = _jwt(uid, nivel="plataforma", papel="admin", tomador_id=None)
    assert client.get("/tipos", headers=_com(forjado)).status_code == 403
    assert client.get("/auth/me", headers=_com(forjado)).json()["nivel"] == "tomador"


# ---------- falha fechada e nível ----------

def test_falha_fechada_sem_segredo(banco, monkeypatch):
    banco.usuario()
    token = _token()  # válido enquanto o segredo existe
    monkeypatch.setattr(config, "AUTH_SEGREDO", "")
    r = _login()
    assert r.status_code == 503 and "AUTH_SEGREDO" in r.json()["detail"]
    assert client.get("/tipos", headers=_com(token)).status_code == 503
    assert client.get("/auth/me", headers=_com(token)).status_code == 503
    assert client.get("/tipos").status_code == 503


def test_login_nao_depende_de_auth_usuario_e_auth_senha(banco, monkeypatch):
    banco.usuario()
    monkeypatch.setattr(config, "AUTH_USUARIO", "")
    monkeypatch.setattr(config, "AUTH_SENHA", "")
    assert _login().status_code == 200


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_tomador_e_prestador_veem_me_mas_nao_os_dados(banco, nivel):
    vinculo = {"tomador_id": banco.tomador()} if nivel == "tomador" else {"prestador_id": banco.prestador()}
    uid = banco.usuario(nivel=nivel, papel="membro", **vinculo)
    token = _token()
    me = client.get("/auth/me", headers=_com(token))
    assert me.status_code == 200
    corpo = me.json()
    assert corpo["id"] == uid and corpo["nivel"] == nivel
    assert corpo[f"{nivel}_id"] == vinculo[f"{nivel}_id"]
    r = client.get("/tipos", headers=_com(token))
    assert r.status_code == 403 and "indisponível" in r.json()["detail"]


def test_health_e_docs_ficam_abertos():
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    try:  # /health toca banco e Redis; nunca devolve 401/503 de autenticação
        codigo = client.get("/health").status_code
    except Exception:
        codigo = 500
    assert codigo not in (401, 503)


def test_openapi_declara_bearer():
    esquemas = client.get("/openapi.json").json()["components"]["securitySchemes"]
    assert any(e.get("scheme") == "bearer" for e in esquemas.values())


def test_cors_preflight_aceita_authorization():
    assert config.CORS_ORIGINS
    for origem in config.CORS_ORIGINS:
        r = client.options("/lotes", headers={"Origin": origem, "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "authorization,content-type"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == origem
        assert "authorization" in r.headers["access-control-allow-headers"].lower()


# ---------- varredura de rotas ----------

ABERTAS = {"/health", "/auth/login", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
QUALQUER_USUARIO = {"/auth/me"}  # autenticada, mas sem exigir nível


def _rotas_de_dados():
    rotas = [r for r in app.routes if isinstance(r, APIRoute) and r.path not in ABERTAS | QUALQUER_USUARIO]
    assert len(rotas) >= 15  # a varredura está olhando as rotas de verdade
    return rotas


def _chamadas(rotas, headers=None):
    for rota in rotas:
        caminho = re.sub(r"\{[^}]+\}", "1", rota.path)
        for metodo in sorted(rota.methods - {"HEAD", "OPTIONS"}):
            yield metodo, rota.path, client.request(metodo, caminho, headers=headers).status_code


def test_varredura_toda_rota_exige_token():
    """Rota nova que esqueça a proteção derruba este teste."""
    abertas = [(m, p, c) for m, p, c in _chamadas(_rotas_de_dados()) if c != 401]
    assert not abertas, f"rotas acessíveis sem token: {abertas}"
    assert client.get("/auth/me").status_code == 401


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_varredura_tomador_e_prestador_recebem_403_em_toda_rota_de_dados(banco, nivel):
    vinculo = {"tomador_id": banco.tomador()} if nivel == "tomador" else {"prestador_id": banco.prestador()}
    banco.usuario(nivel=nivel, papel="admin", **vinculo)
    token = _token()
    liberadas = [(m, p, c) for m, p, c in _chamadas(_rotas_de_dados(), _com(token)) if c != 403]
    assert not liberadas, f"rotas de dados abertas para {nivel}: {liberadas}"


def test_varredura_inclui_imagem_de_pagina():
    caminhos = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert "/lotes/{lote_id}/paginas/{numero}/imagem" in caminhos
    assert client.get("/lotes/1/paginas/1/imagem").status_code == 401
