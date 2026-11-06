from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import FileResponse

from app.routers.lotes import actions
from app.routers.lotes.schemas import LoteCriadoOut, LoteOut
from app.routers.lotes.validations import converter_para_pdf

router = APIRouter(tags=["Lotes"])


@router.post("/lotes", response_model=LoteCriadoOut)
def criar_lote(arquivo: UploadFile = File(...), empresa_id: int | None = Form(None)):
    actions.validar_empresa(empresa_id)  # antes de gravar ou enfileirar qualquer coisa
    dados = arquivo.file.read()
    pdf = converter_para_pdf(dados)
    return actions.criar_lote(dados, pdf, arquivo.filename, empresa_id)


@router.get("/lotes/{lote_id}", response_model=LoteOut)
def obter_lote(lote_id: int):
    return actions.obter_lote(lote_id)


@router.get("/lotes/{lote_id}/paginas/{numero}/imagem")
def imagem_pagina(lote_id: int, numero: int):
    return FileResponse(actions.caminho_imagem_pagina(lote_id, numero), media_type="image/png")
