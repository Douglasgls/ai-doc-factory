from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.organizacoes.schemas import AtivoIn, IdBanco
from app.routers.usuarios import actions
from app.routers.usuarios.schemas import UsuarioListadoOut

router = APIRouter(tags=["Usuários"])  # autenticada (api.py); escopo por organização na action


@router.get("/usuarios", response_model=list[UsuarioListadoOut])
def listar_usuarios(usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    return actions.listar(session, usuario)


@router.patch("/usuarios/{usuario_id}", response_model=UsuarioListadoOut)
def definir_ativo_usuario(usuario_id: IdBanco, corpo: AtivoIn, usuario: UsuarioContexto = Depends(exigir_usuario),
                          session: Session = Depends(get_session)):
    """Plataforma: qualquer usuário. Admin de tomador/prestador: só os da própria organização. Membro: 403.
    Fora do escopo: 404. Desativar a si mesmo: 409."""
    return actions.definir_ativo(session, usuario, usuario_id, corpo.ativo)
