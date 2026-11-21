"""Empresa própria (empresa solo, sem terceirização): o MESMO CNPJ cadastrado como tomador e como prestador, ligados
por um contrato `proprio`, e o convite do administrador (nível prestador). O controle de acesso é o de sempre
(app/escopo.py): o admin é um prestador e só enxerga esse contrato. Uma transação; a linha do prestador fica travada
até o commit (como em terceirizadas.actions), então cadastros simultâneos do mesmo CNPJ se serializam."""
import psycopg
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.escopo import prestador_tem_convite_pendente, prestador_tem_usuario_ativo
from app.models import Contrato, Tomador
from app.routers.auth.actions import UsuarioContexto
from app.routers.convites.actions import criar_na_transacao
from app.routers.empresas_proprias.schemas import NovaEmpresaPropria
from app.routers.terceirizadas.actions import _prestador_travado


def _tomador_travado(session: Session, cnpj: str, nome: str) -> tuple:
    """(id, cnpj, nome, ativo) do tomador do CNPJ, criado se não existir, com a linha travada.

    Um tomador que já existe com este CNPJ é reaproveitado mesmo que tenha usuários ou terceirizadas: é a MESMA
    empresa (mesmo CNPJ), e ela ver os documentos dos próprios funcionários é legítimo. O contrato próprio só liga o
    prestador do CNPJ a ele; o acesso de cada usuário continua sendo o do seu nível (app/escopo.py)."""
    for _ in range(3):
        try:
            session.execute(pg_insert(Tomador).values(cnpj=cnpj, nome=nome)
                            .on_conflict_do_nothing(index_elements=[Tomador.cnpj]))
        except IntegrityError as e:
            # tomador_nome_uniq: outro tomador, de outro CNPJ, já tem este nome; qualquer outro erro sobe como está
            if isinstance(e.orig, psycopg.errors.UniqueViolation) and e.orig.diag.constraint_name == "tomador_nome_uniq":
                raise HTTPException(409, "já existe outro tomador com este nome")
            raise
        linha = session.execute(select(Tomador.id, Tomador.cnpj, Tomador.nome, Tomador.ativo)
                                .where(Tomador.cnpj == cnpj).with_for_update(key_share=True)).first()
        if linha:
            return tuple(linha)
    raise HTTPException(503, "não foi possível cadastrar agora; tente de novo")


def cadastrar(session: Session, corpo: NovaEmpresaPropria, usuario: UsuarioContexto) -> dict:
    prestador_id, p_cnpj, p_nome, p_ativo = _prestador_travado(session, corpo.cnpj, corpo.razao_social)
    tomador_id, t_cnpj, t_nome, t_ativo = _tomador_travado(session, corpo.cnpj, corpo.razao_social)
    if not p_ativo or not t_ativo:
        raise HTTPException(409, "organização desativada")
    contratos = dict(session.execute(select(Contrato.id, Contrato.proprio).where(Contrato.prestador_id == prestador_id)
                                     ).all())
    if any(contratos.values()):
        raise HTTPException(409, "já existe contrato próprio para este CNPJ")
    if contratos:
        raise HTTPException(409, "este CNPJ já é prestador de contratos não próprios (terceirização)")
    contrato = session.execute(
        pg_insert(Contrato).values(tomador_id=tomador_id, prestador_id=prestador_id, proprio=True)
        .on_conflict_do_nothing(index_elements=[Contrato.tomador_id, Contrato.prestador_id])
        .returning(Contrato.id, Contrato.ativo)).first()
    if contrato is None:  # corrida com um contrato criado por fora da trava
        raise HTTPException(409, "já existe contrato entre este tomador e este prestador")
    convite = None
    if prestador_tem_usuario_ativo(session, prestador_id):
        acesso = "ja_tem_acesso"
    elif prestador_tem_convite_pendente(session, prestador_id):
        acesso = "convite_pendente"
    else:
        acesso = "convite_criado"
        c = criar_na_transacao(session, corpo.email_admin, "prestador", "admin", None, prestador_id, usuario.id)
        convite = {k: c[k] for k in ("id", "email", "expira_em", "token")}
    session.commit()
    return {"contrato": {"id": contrato[0], "ativo": contrato[1], "proprio": True},
            "tomador": {"id": tomador_id, "cnpj": t_cnpj, "nome": t_nome},
            "prestador": {"id": prestador_id, "cnpj": p_cnpj, "nome": p_nome},
            "acesso": acesso, "convite": convite}
