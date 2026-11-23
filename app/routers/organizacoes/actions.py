import psycopg
from fastapi import HTTPException
from sqlalchemy import and_, case, exists, false, func, insert, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.escopo import exigir_prestador_sem_empresa_propria, filtro_contrato, filtro_perfil
from app.models import Contrato, Convite, PerfilJornadaCadastro, Prestador, Tomador, Usuario
from app.routers.auth.actions import UsuarioContexto
from app.routers.organizacoes.schemas import NovoContrato, NovoPrestador, NovoTomador

_COLUNAS_TOMADOR = (Tomador.id, Tomador.nome, Tomador.cnpj, Tomador.ativo, Tomador.criado_em)
_COLUNAS_PRESTADOR = (Prestador.id, Prestador.cnpj, Prestador.razao_social, Prestador.ativo, Prestador.criado_em)


def _select_contrato(usuario: UsuarioContexto | None = None):
    """`usuario`: quem lê, para `perfil_jornada_visivel` e `perfil_jornada_nome` (o perfil do contrato pode estar fora
    do escopo dele: o contrato mostra que o perfil existe, sem o nome). None = chamador só da plataforma."""
    tem_usuario = exists().where(Usuario.prestador_id == Prestador.id, Usuario.ativo)
    tem_convite = exists().where(Convite.prestador_id == Prestador.id, Convite.usado_em.is_(None),
                                 Convite.expira_em > func.now())
    acesso = case((tem_usuario, "ativo"), (tem_convite, "convite_pendente"), else_="sem_acesso")
    if usuario is None or usuario.nivel == "plataforma":
        visivel = true()
    else:  # só o admin de empresa própria lê perfis (o contrato dele é o `proprio`); os demais nem o slug detalham
        visivel = func.coalesce(and_(Contrato.proprio, filtro_perfil(usuario)), false())
    return (select(Contrato.id, Contrato.tomador_id, Contrato.prestador_id, Contrato.ativo, Contrato.vigencia_inicio,
                   Contrato.vigencia_fim, Contrato.criado_em, Contrato.perfil_jornada, Contrato.proprio, Tomador.nome, Tomador.ativo, Prestador.razao_social,
                   Prestador.cnpj, Prestador.ativo, acesso, case((visivel, PerfilJornadaCadastro.nome), else_=None),
                   visivel)
            .join(Tomador, Tomador.id == Contrato.tomador_id)
            .join(Prestador, Prestador.id == Contrato.prestador_id)
            .outerjoin(PerfilJornadaCadastro, PerfilJornadaCadastro.perfil == Contrato.perfil_jornada))


def _tomador(l) -> dict:
    return dict(zip(("id", "nome", "cnpj", "ativo", "criado_em"), l))


def _prestador(l) -> dict:
    return dict(zip(("id", "cnpj", "razao_social", "ativo", "criado_em"), l))


def _contrato(l) -> dict:
    return dict(zip(("id", "tomador_id", "prestador_id", "ativo", "vigencia_inicio", "vigencia_fim", "criado_em",
                     "perfil_jornada", "proprio", "tomador_nome", "tomador_ativo", "prestador_razao_social", "prestador_cnpj", "prestador_ativo",
                     "acesso_prestador", "perfil_jornada_nome", "perfil_jornada_visivel"), l))


def _existente(session: Session, consulta) -> int | None:
    """Id da linha que causou o conflito (só para a mensagem); None se já sumiu."""
    return session.execute(consulta).scalar()


def _conflito(entidade: str, onde: str, id_: int | None) -> HTTPException:
    return HTTPException(409, f"já existe {entidade} {id_} com {onde}" if id_ else f"já existe {entidade} com {onde}")


def criar_tomador(session: Session, corpo: NovoTomador) -> dict:
    try:
        linha = session.execute(
            insert(Tomador).values(nome=corpo.nome, cnpj=corpo.cnpj).returning(*_COLUNAS_TOMADOR)).one()
        session.commit()
        return _tomador(linha)
    except IntegrityError as e:
        session.rollback()  # a transação abortou; a consulta do id existente precisa de uma nova
        if not isinstance(e.orig, psycopg.errors.UniqueViolation):
            raise
        if e.orig.diag.constraint_name == "tomador_cnpj_key":
            raise _conflito("o tomador", f"o CNPJ {corpo.cnpj}",
                            _existente(session, select(Tomador.id).where(Tomador.cnpj == corpo.cnpj)))
        raise _conflito("o tomador", f"o nome '{corpo.nome}' (sem diferenciar caixa nem espaços nas pontas)",
                        _existente(session, select(Tomador.id).where(
                            func.lower(func.btrim(Tomador.nome)) == func.lower(func.btrim(corpo.nome)))))


def listar_tomadores(session: Session) -> list[dict]:
    return [_tomador(l) for l in session.execute(select(*_COLUNAS_TOMADOR).order_by(Tomador.id))]


def criar_prestador(session: Session, corpo: NovoPrestador) -> dict:
    try:
        linha = session.execute(insert(Prestador).values(cnpj=corpo.cnpj, razao_social=corpo.razao_social)
                                .returning(*_COLUNAS_PRESTADOR)).one()
        session.commit()
        return _prestador(linha)
    except IntegrityError as e:
        session.rollback()
        if not isinstance(e.orig, psycopg.errors.UniqueViolation):
            raise
        raise _conflito("o prestador", f"o CNPJ {corpo.cnpj}",
                        _existente(session, select(Prestador.id).where(Prestador.cnpj == corpo.cnpj)))


def listar_prestadores(session: Session) -> list[dict]:
    return [_prestador(l) for l in session.execute(select(*_COLUNAS_PRESTADOR).order_by(Prestador.id))]


def criar_contrato(session: Session, corpo: NovoContrato) -> dict:
    exigir_prestador_sem_empresa_propria(session, corpo.prestador_id)
    try:
        id_ = session.execute(insert(Contrato).values(
            tomador_id=corpo.tomador_id, prestador_id=corpo.prestador_id, vigencia_inicio=corpo.vigencia_inicio,
            vigencia_fim=corpo.vigencia_fim).returning(Contrato.id)).scalar_one()
        linha = session.execute(_select_contrato().where(Contrato.id == id_)).one()
        session.commit()
        return _contrato(linha)
    except IntegrityError as e:
        session.rollback()
        erro = e.orig
        if isinstance(erro, psycopg.errors.UniqueViolation):
            raise _conflito("o contrato", f"o tomador {corpo.tomador_id} e o prestador {corpo.prestador_id}",
                            _existente(session, select(Contrato.id).where(
                                Contrato.tomador_id == corpo.tomador_id, Contrato.prestador_id == corpo.prestador_id)))
        if isinstance(erro, psycopg.errors.ForeignKeyViolation):
            quem = "prestador" if "prestador" in (erro.diag.constraint_name or "") else "tomador"
            id_ = corpo.prestador_id if quem == "prestador" else corpo.tomador_id
            raise HTTPException(404, f"{quem} {id_} não encontrado")
        if isinstance(erro, psycopg.errors.CheckViolation):  # contrato_vigencia_check (o schema já recusa antes)
            raise HTTPException(422, "vigencia_fim não pode ser anterior a vigencia_inicio")
        raise


def listar_contratos(session: Session, tomador_id: int | None = None, prestador_id: int | None = None, *,
                     usuario: UsuarioContexto) -> list[dict]:
    """Contratos no escopo de `usuario` (obrigatório), com filtros opcionais por tomador e prestador."""
    consulta = _select_contrato(usuario).where(filtro_contrato(usuario))
    if tomador_id is not None:
        consulta = consulta.where(Contrato.tomador_id == tomador_id)
    if prestador_id is not None:
        consulta = consulta.where(Contrato.prestador_id == prestador_id)
    return [_contrato(l) for l in session.execute(consulta.order_by(Contrato.id))]


def _nao_encontrado(entidade: str, id_: int) -> HTTPException:
    return HTTPException(404, f"{entidade} {id_} não encontrado")


def definir_ativo_tomador(session: Session, id_: int, ativo: bool) -> dict:
    """Idempotente: repetir o valor devolve o recurso. Os dados ligados (lotes, usuários) não são tocados."""
    linha = session.execute(update(Tomador).where(Tomador.id == id_).values(ativo=ativo)
                            .returning(*_COLUNAS_TOMADOR)).first()
    if linha is None:
        raise _nao_encontrado("tomador", id_)
    session.commit()
    return _tomador(linha)


def definir_ativo_prestador(session: Session, id_: int, ativo: bool) -> dict:
    linha = session.execute(update(Prestador).where(Prestador.id == id_).values(ativo=ativo)
                            .returning(*_COLUNAS_PRESTADOR)).first()
    if linha is None:
        raise _nao_encontrado("prestador", id_)
    session.commit()
    return _prestador(linha)


def definir_ativo_contrato(session: Session, id_: int, ativo: bool) -> dict:
    if session.execute(update(Contrato).where(Contrato.id == id_).values(ativo=ativo)
                       .returning(Contrato.id)).first() is None:
        raise _nao_encontrado("contrato", id_)
    linha = session.execute(_select_contrato().where(Contrato.id == id_)).one()
    session.commit()
    return _contrato(linha)
