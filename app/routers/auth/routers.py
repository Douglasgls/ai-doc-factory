from fastapi import APIRouter, Depends

from app.routers.auth import actions
from app.routers.auth.schemas import LoginIn, TokenOut, UsuarioOut

router = APIRouter(tags=["Autenticação"])


@router.post("/auth/login", response_model=TokenOut)
def login(dados: LoginIn):
    return actions.login(dados.usuario, dados.senha)


@router.get("/auth/me", response_model=UsuarioOut)
def me(usuario: str = Depends(actions.exigir_usuario)):
    return {"usuario": usuario}
