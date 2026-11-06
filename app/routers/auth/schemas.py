from pydantic import BaseModel


class LoginIn(BaseModel):
    usuario: str
    senha: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: str  # ISO 8601 em UTC


class UsuarioOut(BaseModel):
    usuario: str
