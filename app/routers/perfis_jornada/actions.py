"""Perfis de jornada (Goal 6) e a associação ao contrato. Só a plataforma (app/api.py). A herança e a vigência por
data ficam em app/ponto.py; aqui só se grava e se lê."""
from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from app import ponto
from app.models import Contrato, PerfilJornada
from app.routers.organizacoes import actions as organizacoes
from app.routers.perfis_jornada.schemas import PerfilEntrada

_COLUNAS = (PerfilJornada.parametro, PerfilJornada.valor, PerfilJornada.base_legal, PerfilJornada.vigente_desde,
            PerfilJornada.unidade)


def _linhas(session: Session, perfil: str) -> list:
    return list(session.execute(
        select(*_COLUNAS).where(PerfilJornada.perfil == perfil)
        .order_by(PerfilJornada.parametro, PerfilJornada.vigente_desde.asc().nulls_first())))


def _perfil(session: Session, perfil: str) -> dict:
    padrao = _linhas(session, ponto.PERFIL_PADRAO)
    proprios = padrao if perfil == ponto.PERFIL_PADRAO else _linhas(session, perfil)
    if not proprios:
        raise HTTPException(404, f"perfil '{perfil}' não encontrado")
    return {
        "perfil": perfil, "padrao": perfil == ponto.PERFIL_PADRAO,
        "proprios": [{"parametro": p, "valor": float(v), "unidade": u, "base_legal": b, "vigente_desde": d}
                     for p, v, b, d, u in proprios],
        "efetivo": ponto.herdar([tuple(l)[:4] for l in padrao], [tuple(l)[:4] for l in proprios]),
    }


def listar_perfis(session: Session) -> list[dict]:
    contratos = {nome: n for nome, n in session.execute(
        select(Contrato.perfil_jornada, func.count()).group_by(Contrato.perfil_jornada))}
    linhas = session.execute(
        select(PerfilJornada.perfil, func.count(func.distinct(PerfilJornada.parametro)))
        .group_by(PerfilJornada.perfil).order_by(PerfilJornada.perfil))
    return [{"perfil": nome, "padrao": nome == ponto.PERFIL_PADRAO, "parametros_proprios": n,
             "contratos": contratos.get(nome, 0)} for nome, n in linhas]


def obter_perfil(session: Session, perfil: str) -> dict:
    return _perfil(session, perfil)


def gravar_perfil(session: Session, perfil: str, corpo: PerfilEntrada) -> dict:
    """Cria o perfil ou substitui TODOS os seus parâmetros próprios (idempotente). O perfil padrão não é alterado
    pela API: ele é a referência legal e muda só por migração."""
    if perfil == ponto.PERFIL_PADRAO:
        raise HTTPException(409, f"o perfil '{ponto.PERFIL_PADRAO}' é a referência e não é alterado pela API")
    unidades = {p: u for p, u in session.execute(
        select(PerfilJornada.parametro, PerfilJornada.unidade)
        .where(PerfilJornada.perfil == ponto.PERFIL_PADRAO, PerfilJornada.vigente_desde.is_(None)))}
    desconhecidos = sorted({p.parametro for p in corpo.parametros} - set(unidades))
    if desconhecidos:
        raise HTTPException(422, f"parâmetro desconhecido: {', '.join(desconhecidos)}; "
                                 f"válidos: {', '.join(sorted(unidades))}")
    session.execute(delete(PerfilJornada).where(PerfilJornada.perfil == perfil)
                    .execution_options(synchronize_session=False))
    session.execute(insert(PerfilJornada), [
        {"perfil": perfil, "parametro": p.parametro, "valor": p.valor, "unidade": unidades[p.parametro],
         "base_legal": p.base_legal, "vigente_desde": p.vigente_desde} for p in corpo.parametros])
    resultado = _perfil(session, perfil)
    session.commit()
    return resultado


def associar_perfil(session: Session, contrato_id: int, perfil: str) -> dict:
    """Aponta o contrato para o perfil. Vale para as análises feitas a partir daí; as já gravadas não mudam
    (cada uma guarda o perfil que usou) até o documento ser reprocessado."""
    if perfil != ponto.PERFIL_PADRAO and session.execute(
            select(PerfilJornada.id).where(PerfilJornada.perfil == perfil).limit(1)).first() is None:
        raise HTTPException(404, f"perfil '{perfil}' não encontrado")
    if session.execute(update(Contrato).where(Contrato.id == contrato_id).values(perfil_jornada=perfil)
                       .returning(Contrato.id)).first() is None:
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")
    linha = session.execute(organizacoes._select_contrato().where(Contrato.id == contrato_id)).one()
    session.commit()
    return organizacoes._contrato(linha)
