from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_session
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.busca import actions
from app.routers.busca.schemas import ResultadoBuscaOut
from app.routers.busca.validations import validar_consulta

router = APIRouter(tags=["Busca"])


@router.get("/busca", response_model=list[ResultadoBuscaOut])
def busca(q: str = Query(""), limite: int = Query(20, ge=1, le=100),
          usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    validar_consulta(q)
    return actions.buscar(session, q, limite, usuario)
