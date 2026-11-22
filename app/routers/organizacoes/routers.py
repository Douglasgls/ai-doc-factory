from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_session

from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.organizacoes import actions
from app.routers.organizacoes.schemas import (
    AtivoIn, ContratoOut, IdBanco, NovoContrato, NovoPrestador, NovoTomador, PrestadorOut, TomadorOut)

router = APIRouter(tags=["Organizações"])  # só plataforma (api.py)
router_leitura = APIRouter(tags=["Organizações"])  # leitura de contratos filtrada pelo escopo do usuário


@router.post("/tomadores", status_code=201, response_model=TomadorOut)
def criar_tomador(corpo: NovoTomador, session: Session = Depends(get_session)):
    return actions.criar_tomador(session, corpo)


@router.get("/tomadores", response_model=list[TomadorOut])
def listar_tomadores(session: Session = Depends(get_session)):
    return actions.listar_tomadores(session)


@router.patch("/tomadores/{tomador_id}", response_model=TomadorOut)
def definir_ativo_tomador(tomador_id: IdBanco, corpo: AtivoIn, session: Session = Depends(get_session)):
    return actions.definir_ativo_tomador(session, tomador_id, corpo.ativo)


@router.post("/prestadores", status_code=201, response_model=PrestadorOut)
def criar_prestador(corpo: NovoPrestador, session: Session = Depends(get_session)):
    return actions.criar_prestador(session, corpo)


@router.get("/prestadores", response_model=list[PrestadorOut])
def listar_prestadores(session: Session = Depends(get_session)):
    return actions.listar_prestadores(session)


@router.patch("/prestadores/{prestador_id}", response_model=PrestadorOut)
def definir_ativo_prestador(prestador_id: IdBanco, corpo: AtivoIn, session: Session = Depends(get_session)):
    return actions.definir_ativo_prestador(session, prestador_id, corpo.ativo)


@router.post("/contratos", status_code=201, response_model=ContratoOut)
def criar_contrato(corpo: NovoContrato, session: Session = Depends(get_session)):
    return actions.criar_contrato(session, corpo)


@router.patch("/contratos/{contrato_id}", response_model=ContratoOut)
def definir_ativo_contrato(contrato_id: IdBanco, corpo: AtivoIn, session: Session = Depends(get_session)):
    return actions.definir_ativo_contrato(session, contrato_id, corpo.ativo)


@router_leitura.get("/contratos", response_model=list[ContratoOut])
def listar_contratos(tomador_id: Annotated[IdBanco | None, Query()] = None,
                     prestador_id: Annotated[IdBanco | None, Query()] = None,
                     usuario: UsuarioContexto = Depends(exigir_usuario),
                     session: Session = Depends(get_session)):
    """Filtros opcionais por tomador e por prestador. Plataforma vê todos; tomador, os do seu tomador;
    prestador, só os ativos dele."""
    return actions.listar_contratos(session, tomador_id, prestador_id, usuario=usuario)
