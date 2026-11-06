"""Autenticação de um único administrador (variáveis de ambiente). JWT HS256 com PyJWT.
Falha fechada: sem AUTH_USUARIO/AUTH_SENHA/AUTH_SEGREDO nada é liberado."""
import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app import config

ALGORITMO = "HS256"
bearer = HTTPBearer(auto_error=False, description="Token obtido em POST /auth/login")


def _configurado() -> bool:
    return bool(config.AUTH_USUARIO and config.AUTH_SENHA and config.AUTH_SEGREDO)


def _exigir_configuracao() -> None:
    if not _configurado():
        raise HTTPException(503, "autenticação não configurada: defina AUTH_USUARIO, AUTH_SENHA e AUTH_SEGREDO")


def _iguais(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def login(usuario: str, senha: str) -> dict:
    _exigir_configuracao()
    usuario_ok = _iguais(usuario, config.AUTH_USUARIO)
    senha_ok = _iguais(senha, config.AUTH_SENHA)  # sempre avalia os dois: mesma resposta e mesmo trabalho
    if not (usuario_ok and senha_ok):
        raise HTTPException(401, "usuário ou senha inválidos", headers={"WWW-Authenticate": "Bearer"})
    agora = datetime.now(timezone.utc)
    expira = agora + timedelta(minutes=config.AUTH_EXPIRA_MIN)
    token = jwt.encode({"sub": usuario, "iat": int(agora.timestamp()), "exp": int(expira.timestamp())},
                       config.AUTH_SEGREDO, algorithm=ALGORITMO)
    return {"access_token": token, "token_type": "bearer", "expira_em": expira.isoformat()}


def exigir_usuario(credenciais: HTTPAuthorizationCredentials | None = Depends(bearer)) -> str:
    """Dependência das rotas protegidas: devolve o usuário do token ou recusa."""
    _exigir_configuracao()
    negado = HTTPException(401, "não autenticado", headers={"WWW-Authenticate": "Bearer"})
    if credenciais is None:
        raise negado
    try:
        dados = jwt.decode(credenciais.credentials, config.AUTH_SEGREDO, algorithms=[ALGORITMO],
                           options={"require": ["sub", "iat", "exp"]})
    except jwt.PyJWTError:
        raise negado
    sub = dados.get("sub")
    if not isinstance(sub, str) or not _iguais(sub, config.AUTH_USUARIO):
        raise negado
    return sub
