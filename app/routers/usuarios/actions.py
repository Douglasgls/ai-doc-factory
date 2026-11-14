from fastapi import HTTPException
from sqlalchemy import select, true
from sqlalchemy.orm import Session

from app.models import Usuario
from app.routers.auth.actions import UsuarioContexto

_CHAVES = ("id", "nome", "email", "nivel", "papel", "ativo", "criado_em")


def listar(session: Session, usuario: UsuarioContexto) -> list[dict]:
    """Plataforma: todos. Admin de tomador/prestador: os da própria organização. Membro: 403."""
    if usuario.nivel == "plataforma":
        onde = true()
    elif usuario.papel != "admin":
        raise HTTPException(403, "apenas administradores listam usuários")
    elif usuario.nivel == "tomador" and usuario.tomador_id is not None:
        onde = Usuario.tomador_id == usuario.tomador_id
    elif usuario.nivel == "prestador" and usuario.prestador_id is not None:
        onde = Usuario.prestador_id == usuario.prestador_id
    else:
        raise HTTPException(403, "sem permissão para listar usuários")
    linhas = session.execute(select(*(getattr(Usuario, c) for c in _CHAVES)).where(onde).order_by(Usuario.id))
    return [dict(zip(_CHAVES, l)) for l in linhas]
