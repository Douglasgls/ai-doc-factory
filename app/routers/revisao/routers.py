from fastapi import APIRouter

from app.routers.revisao import actions
from app.routers.revisao.schemas import ItemFilaRevisaoOut, Revisao, RevisaoOut

router = APIRouter(tags=["Revisão"])


@router.get("/revisao", response_model=list[ItemFilaRevisaoOut])
def fila_revisao():
    return actions.fila_revisao()


@router.post("/documentos/{documento_id}/revisao", response_model=RevisaoOut)
def revisar_documento(documento_id: int, revisao: Revisao):
    return actions.revisar_documento(documento_id, revisao)
