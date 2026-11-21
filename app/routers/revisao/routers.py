from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.escopo import documento_para_escrita
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.revisao import actions
from app.routers.revisao.schemas import ItemFilaRevisaoOut, Revisao, RevisaoOut

router = APIRouter(tags=["Revisão"])


@router.get("/revisao", response_model=list[ItemFilaRevisaoOut])
def fila_revisao(usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    return actions.fila_revisao(session, usuario)


@router.post("/documentos/{documento_id}/revisao", response_model=RevisaoOut,
             dependencies=[Depends(documento_para_escrita)])
def revisar_documento(documento_id: int, revisao: Revisao, usuario: UsuarioContexto = Depends(exigir_usuario),
                      session: Session = Depends(get_session)):
    return actions.revisar_documento(session, documento_id, revisao, usuario.email)
