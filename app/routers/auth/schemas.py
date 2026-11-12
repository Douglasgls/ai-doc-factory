from pydantic import BaseModel


class LoginIn(BaseModel):
    usuario: str
    senha: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: str  # ISO 8601 em UTC


class UsuarioOut(BaseModel):
    id: int
    email: str
    nome: str
    nivel: str
    papel: str
    tomador_id: int | None = None
    prestador_id: int | None = None
    usuario: str  # igual a `email`; mantido por compatibilidade com o formato anterior de /auth/me
