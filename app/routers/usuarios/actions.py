from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.escopo import filtro_usuario_gerenciavel, motivo_recusa_gestao_usuario
from app.models import Usuario
from app.routers.auth.actions import UsuarioContexto

_CHAVES = ("id", "nome", "email", "nivel", "papel", "ativo", "criado_em")


def listar(session: Session, usuario: UsuarioContexto) -> list[dict]:
    """Plataforma: todos. Admin de tomador/prestador: os da própria organização. Membro: 403."""
    onde = filtro_usuario_gerenciavel(usuario)
    if onde is None:
        raise HTTPException(403, "apenas administradores listam usuários")
    linhas = session.execute(select(*(getattr(Usuario, c) for c in _CHAVES)).where(onde).order_by(Usuario.id))
    return [dict(zip(_CHAVES, l)) for l in linhas]


def definir_ativo(session: Session, usuario: UsuarioContexto, alvo_id: int, ativo: bool) -> dict:
    """Ativa/desativa um usuário (regras em escopo.motivo_recusa_gestao_usuario). Idempotente. O token do usuário
    desativado deixa de valer na hora: exigir_usuario confere `ativo` no banco a cada requisição."""
    recusa = motivo_recusa_gestao_usuario(session, usuario, alvo_id, ativo)
    if recusa is not None:
        raise HTTPException(*recusa)
    linha = session.execute(update(Usuario).where(Usuario.id == alvo_id).values(ativo=ativo)
                            .returning(*(getattr(Usuario, c) for c in _CHAVES))).one()
    session.commit()
    return dict(zip(_CHAVES, linha))
