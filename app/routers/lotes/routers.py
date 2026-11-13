import asyncio
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from app.routers.lotes import actions
from app.routers.lotes.schemas import LoteCriadoOut, LoteOut
from app.routers.lotes.validations import converter_para_pdf

router = APIRouter(tags=["Lotes"])


@router.post("/lotes", response_model=LoteCriadoOut, response_model_exclude_unset=True)
def criar_lote(arquivo: UploadFile = File(...), empresa_id: int | None = Form(None)):
    actions.validar_empresa(empresa_id)  # antes de gravar ou enfileirar qualquer coisa
    dados = arquivo.file.read()
    pdf = converter_para_pdf(dados)
    return actions.criar_lote(dados, pdf, arquivo.filename, empresa_id)


@router.get("/lotes/{lote_id}", response_model=LoteOut, response_model_exclude_unset=True)
def obter_lote(lote_id: int):
    return actions.obter_lote(lote_id)


@router.get("/lotes/{lote_id}/eventos")
async def eventos_lote(lote_id: int, request: Request, once: bool = False):
    await asyncio.to_thread(actions.obter_lote, lote_id)  # garante 404 imediato sem bloquear o event loop
    return StreamingResponse(
        actions.stream_eventos_lote(lote_id, request, once=once),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/lotes/{lote_id}/cancelar")
def cancelar_lote(lote_id: int):
    return actions.cancelar_lote(lote_id)


@router.post("/lotes/{lote_id}/reprocessar")
def reprocessar_lote(lote_id: int):
    return actions.reprocessar_lote(lote_id)


@router.get("/lotes/{lote_id}/paginas/{numero}/imagem")
def imagem_pagina(lote_id: int, numero: int):
    return FileResponse(actions.caminho_imagem_pagina(lote_id, numero), media_type="image/png")
