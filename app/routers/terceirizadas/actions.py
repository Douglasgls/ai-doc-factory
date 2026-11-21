"""Cadastro de terceirizada pelo cliente. Uma transação: prestador (reutiliza o do mesmo CNPJ, sem alterar a razão
social), contrato ativo e, se o prestador ainda não tem acesso, o convite do administrador dele. A linha do prestador
fica travada até o commit, então cadastros simultâneos do mesmo CNPJ se serializam: um prestador, um contrato por
tomador e no máximo um convite."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.escopo import prestador_tem_convite_pendente, prestador_tem_usuario_ativo
from app.models import Contrato, Prestador, Tomador
from app.routers.auth.actions import UsuarioContexto
from app.routers.convites.actions import criar_na_transacao
from app.routers.terceirizadas.schemas import NovaTerceirizada


def _tomador_alvo(usuario: UsuarioContexto, corpo: NovaTerceirizada) -> int:
    if usuario.nivel == "plataforma":
        if corpo.tomador_id is None:
            raise HTTPException(422, "tomador_id é obrigatório para a plataforma")
        return corpo.tomador_id
    if usuario.nivel != "tomador" or usuario.papel != "admin" or usuario.tomador_id is None:
        raise HTTPException(403, "apenas o administrador do tomador cadastra terceirizadas")
    if corpo.tomador_id is not None and corpo.tomador_id != usuario.tomador_id:
        raise HTTPException(403, "tomador_id diferente do seu")
    return usuario.tomador_id


def _prestador_travado(session: Session, cnpj: str, razao_social: str) -> tuple:
    """(id, cnpj, razao_social, ativo) do prestador do CNPJ, criado se não existir, com a linha travada."""
    for _ in range(3):
        session.execute(pg_insert(Prestador).values(cnpj=cnpj, razao_social=razao_social)
                        .on_conflict_do_nothing(index_elements=[Prestador.cnpj]))
        linha = session.execute(
            select(Prestador.id, Prestador.cnpj, Prestador.razao_social, Prestador.ativo)
            .where(Prestador.cnpj == cnpj).with_for_update(key_share=True)).first()
        if linha:
            return tuple(linha)
    raise HTTPException(503, "não foi possível cadastrar agora; tente de novo")


def cadastrar(session: Session, corpo: NovaTerceirizada, usuario: UsuarioContexto) -> dict:
    tomador_id = _tomador_alvo(usuario, corpo)
    ativo = session.execute(select(Tomador.ativo).where(Tomador.id == tomador_id)).first()
    if ativo is None or not ativo[0]:
        raise HTTPException(404, "tomador não encontrado ou desativado")
    prestador_id, cnpj, razao_social, prestador_ativo = _prestador_travado(session, corpo.cnpj, corpo.razao_social)
    if not prestador_ativo:
        raise HTTPException(409, "terceirizada desativada")
    if session.execute(select(Contrato.id).where(Contrato.prestador_id == prestador_id, Contrato.proprio).limit(1)
                       ).first():  # o admin da empresa própria passaria a ver os lotes deste tomador
        raise HTTPException(409, "este CNPJ é uma empresa própria e não pode ser terceirizada")
    contrato = session.execute(
        pg_insert(Contrato).values(tomador_id=tomador_id, prestador_id=prestador_id)
        .on_conflict_do_nothing(index_elements=[Contrato.tomador_id, Contrato.prestador_id])
        .returning(Contrato.id, Contrato.ativo)).first()
    if contrato is None:
        raise HTTPException(409, "terceirizada já cadastrada")
    convite = None
    if prestador_tem_usuario_ativo(session, prestador_id):
        acesso = "ja_tem_acesso"
    elif prestador_tem_convite_pendente(session, prestador_id):
        acesso = "convite_pendente"
    else:
        acesso = "convite_criado"
        c = criar_na_transacao(session, corpo.email, "prestador", "admin", None, prestador_id, usuario.id)
        convite = {k: c[k] for k in ("id", "email", "expira_em", "token")}
    session.commit()
    return {"contrato": {"id": contrato[0], "ativo": contrato[1]},
            "prestador": {"id": prestador_id, "cnpj": cnpj, "razao_social": razao_social},
            "acesso": acesso, "convite": convite}
