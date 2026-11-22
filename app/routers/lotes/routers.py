import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_session
from app.escopo import lote_para_escrita, lote_para_leitura
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.lotes import actions
from app.routers.lotes.schemas import LoteCriadoOut, LoteOut, LotesListadosOut
from app.routers.organizacoes.schemas import IdBanco
from app.routers.lotes.validations import converter_para_pdf, ler_com_limite, validar_paginas

router = APIRouter(tags=["Lotes"])


@router.post("/lotes", response_model=LoteCriadoOut, response_model_exclude_unset=True)
def criar_lote(arquivo: UploadFile = File(...), contrato_id: Annotated[IdBanco | None, Form()] = None,
               usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    """`contrato_id`: contrato em que o lote entra. Plataforma: opcional; 404 se não existe, 409 se está inativo.
    Prestador: obrigatório (422) e tem que ser contrato ativo dele (404 se fora do escopo). Tomador: 403.
    O mesmo arquivo em contratos diferentes gera lotes diferentes."""
    actions.validar_contrato(session, contrato_id, usuario)  # antes de gravar ou enfileirar qualquer coisa
    dados = ler_com_limite(arquivo)
    pdf = converter_para_pdf(dados)
    validar_paginas(pdf)
    return actions.criar_lote(session, dados, pdf, arquivo.filename, contrato_id)


@router.get("/lotes", response_model=LotesListadosOut)
def listar_lotes(limite: Annotated[int, Query(ge=1, le=100)] = 20, antes_de: Annotated[IdBanco | None, Query()] = None,
                 estado: Annotated[str | None, Query()] = None, contrato_id: Annotated[IdBanco | None, Query()] = None,
                 usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    """Resumo dos lotes do escopo do usuário, do mais novo para o mais antigo. `antes_de`: cursor por id (use
    `proximo_cursor`). Filtros: `estado`, `contrato_id` (404 se fora do escopo). Detalhes: GET /lotes/{id}."""
    return actions.listar_lotes(session, usuario=usuario, limite=limite, antes_de=antes_de, estado=estado,
                                contrato_id=contrato_id)


@router.get("/lotes/{lote_id}", response_model=LoteOut, response_model_exclude_unset=True,
            dependencies=[Depends(lote_para_leitura)])
def obter_lote(lote_id: int, session: Session = Depends(get_session)):
    return actions.obter_lote(session, lote_id)


@router.get("/lotes/{lote_id}/eventos", dependencies=[Depends(lote_para_leitura)])
async def eventos_lote(lote_id: int, request: Request, once: bool = False):
    await asyncio.to_thread(actions.montar_pacote_evento, lote_id)  # garante 404 imediato sem bloquear o event loop
    return StreamingResponse(
        actions.stream_eventos_lote(lote_id, request, once=once),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/lotes/{lote_id}/cancelar", dependencies=[Depends(lote_para_escrita)])
def cancelar_lote(lote_id: int, session: Session = Depends(get_session)):
    return actions.cancelar_lote(session, lote_id)


@router.post("/lotes/{lote_id}/reprocessar", dependencies=[Depends(lote_para_escrita)])
def reprocessar_lote(lote_id: int, session: Session = Depends(get_session)):
    return actions.reprocessar_lote(session, lote_id)


@router.get("/lotes/{lote_id}/paginas/{numero}/imagem", dependencies=[Depends(lote_para_leitura)])
def imagem_pagina(lote_id: int, numero: int):
    return FileResponse(actions.caminho_imagem_pagina(lote_id, numero), media_type="image/png")
