"""Autenticação: login, JWT, falha fechada e varredura de todas as rotas. Sem rede; só valores falsos de teste."""
import re
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import config
from app.api import app

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

USUARIO, SENHA = "usuario-teste", "senha-falsa-teste"


def _token(**sobrescrever):
    agora = datetime.now(timezone.utc)
    claims = {"sub": USUARIO, "iat": int(agora.timestamp()), "exp": int((agora + timedelta(minutes=5)).timestamp())}
    claims.update(sobrescrever)
    return jwt.encode(claims, config.AUTH_SEGREDO, algorithm="HS256")


def _com(token):
    return {"Authorization": f"Bearer {token}"}


def test_login_certo_devolve_token_valido():
    r = client.post("/auth/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["token_type"] == "bearer" and corpo["expira_em"]
    claims = jwt.decode(corpo["access_token"], config.AUTH_SEGREDO, algorithms=["HS256"])
    assert claims["sub"] == USUARIO and claims["exp"] > claims["iat"]
    assert claims["exp"] - claims["iat"] == config.AUTH_EXPIRA_MIN * 60


def test_token_do_login_acessa_rota_protegida():
    token = client.post("/auth/login", json={"usuario": USUARIO, "senha": SENHA}).json()["access_token"]
    assert client.get("/auth/me", headers=_com(token)).json() == {"usuario": USUARIO}
    assert client.get("/tipos", headers=_com(token)).status_code == 200


def test_usuario_errado_e_senha_errada_dao_a_mesma_resposta():
    a = client.post("/auth/login", json={"usuario": "outro", "senha": SENHA})
    b = client.post("/auth/login", json={"usuario": USUARIO, "senha": "errada"})
    c = client.post("/auth/login", json={"usuario": "outro", "senha": "errada"})
    assert a.status_code == b.status_code == c.status_code == 401
    assert a.json() == b.json() == c.json()


def test_login_com_caracteres_nao_ascii_nao_quebra():
    r = client.post("/auth/login", json={"usuario": "usuário-ç", "senha": "sênha-ã"})
    assert r.status_code == 401


def test_senha_nao_vai_para_o_log(caplog):
    with caplog.at_level("DEBUG"):
        client.post("/auth/login", json={"usuario": USUARIO, "senha": "senha-errada-xyz"})
    assert "senha-errada-xyz" not in caplog.text


def test_sem_token_responde_401_com_www_authenticate():
    r = client.get("/tipos")
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("cabecalho", ["Bearer", "Bearer lixo.sem.sentido", "Basic abc", "Bearer a.b", "token"])
def test_token_malformado(cabecalho):
    r = client.get("/tipos", headers={"Authorization": cabecalho})
    assert r.status_code == 401


def test_token_expirado():
    passado = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp())
    r = client.get("/tipos", headers=_com(_token(exp=passado)))
    assert r.status_code == 401


def test_token_assinado_com_outro_segredo():
    agora = int(datetime.now(timezone.utc).timestamp())
    falso = jwt.encode({"sub": USUARIO, "iat": agora, "exp": agora + 300}, "outro-segredo-falso-com-mais-de-32-bytes!",
                       algorithm="HS256")
    assert client.get("/tipos", headers=_com(falso)).status_code == 401


def test_token_com_alg_none():
    agora = int(datetime.now(timezone.utc).timestamp())
    sem_assinatura = jwt.encode({"sub": USUARIO, "iat": agora, "exp": agora + 300}, key=None, algorithm="none")
    assert client.get("/tipos", headers=_com(sem_assinatura)).status_code == 401


def test_token_com_outro_algoritmo_hmac():
    agora = int(datetime.now(timezone.utc).timestamp())
    hs512 = jwt.encode({"sub": USUARIO, "iat": agora, "exp": agora + 300}, config.AUTH_SEGREDO, algorithm="HS512")
    assert client.get("/tipos", headers=_com(hs512)).status_code == 401


def test_token_sem_exp_ou_de_outro_usuario():
    agora = int(datetime.now(timezone.utc).timestamp())
    sem_exp = jwt.encode({"sub": USUARIO, "iat": agora}, config.AUTH_SEGREDO, algorithm="HS256")
    assert client.get("/tipos", headers=_com(sem_exp)).status_code == 401
    assert client.get("/tipos", headers=_com(_token(sub="outro"))).status_code == 401


def test_token_na_query_string_nao_vale():
    token = _token()
    assert client.get("/tipos", params={"token": token, "access_token": token}).status_code == 401


@pytest.mark.parametrize("faltando", ["AUTH_USUARIO", "AUTH_SENHA", "AUTH_SEGREDO"])
def test_falha_fechada_sem_configuracao(monkeypatch, faltando):
    token = _token()  # válido enquanto o segredo existe
    monkeypatch.setattr(config, faltando, "")
    r = client.post("/auth/login", json={"usuario": USUARIO, "senha": SENHA})
    assert r.status_code == 503 and "AUTH_" in r.json()["detail"]
    assert client.get("/tipos", headers=_com(token)).status_code == 503
    assert client.get("/tipos").status_code == 503


def test_falha_fechada_nao_aceita_credencial_vazia(monkeypatch):
    for campo in ("AUTH_USUARIO", "AUTH_SENHA", "AUTH_SEGREDO"):
        monkeypatch.setattr(config, campo, "")
    assert client.post("/auth/login", json={"usuario": "", "senha": ""}).status_code == 503


def test_health_e_docs_ficam_abertos():
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    # /health toca banco e Redis; sem eles responde 500, mas nunca 401/503 de autenticação
    try:
        codigo = client.get("/health").status_code
    except Exception:
        codigo = 500
    assert codigo not in (401, 503)


def test_openapi_declara_bearer():
    esquemas = client.get("/openapi.json").json()["components"]["securitySchemes"]
    assert any(e.get("scheme") == "bearer" for e in esquemas.values())


def test_cors_preflight_aceita_authorization():
    assert config.CORS_ORIGINS  # origens vêm do ambiente (padrão: Vite em 5173)
    for origem in config.CORS_ORIGINS:
        r = client.options("/lotes", headers={"Origin": origem, "Access-Control-Request-Method": "POST",
                                              "Access-Control-Request-Headers": "authorization,content-type"})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == origem
        assert "authorization" in r.headers["access-control-allow-headers"].lower()


ABERTAS = {"/health", "/auth/login", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def test_varredura_toda_rota_exige_token():
    """Percorre app.routes: qualquer rota nova que esqueça a dependência derruba este teste."""
    rotas = [r for r in app.routes if isinstance(r, APIRoute) and r.path not in ABERTAS]
    assert len(rotas) >= 15 # garante que a varredura está olhando as rotas de verdade
    sem_protecao = []
    for rota in rotas:
        caminho = re.sub(r"\{[^}]+\}", "1", rota.path)
        for metodo in rota.methods - {"HEAD", "OPTIONS"}:
            r = client.request(metodo, caminho)
            if r.status_code != 401:
                sem_protecao.append((metodo, rota.path, r.status_code))
    assert not sem_protecao, f"rotas acessíveis sem token: {sem_protecao}"


def test_varredura_inclui_imagem_de_pagina():
    caminhos = {r.path for r in app.routes if isinstance(r, APIRoute)}
    assert "/lotes/{lote_id}/paginas/{numero}/imagem" in caminhos
    assert client.get("/lotes/1/paginas/1/imagem").status_code == 401
