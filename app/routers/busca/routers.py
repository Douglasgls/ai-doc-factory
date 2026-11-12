from fastapi import APIRouter, Query

from app.routers.busca import actions
from app.routers.busca.schemas import ResultadoBuscaOut
from app.routers.busca.validations import validar_consulta

router = APIRouter(tags=["Busca"])


@router.get("/busca", response_model=list[ResultadoBuscaOut])
def busca(q: str = Query(""), limite: int = Query(20, ge=1, le=100)):
    validar_consulta(q)
    return actions.buscar(q, limite)
