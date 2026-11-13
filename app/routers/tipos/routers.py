from fastapi import APIRouter

from app.routers.tipos import actions
from app.routers.tipos.schemas import TipoOut

router = APIRouter(tags=["Tipos"])


@router.get("/tipos", response_model=list[TipoOut])
def listar_tipos():
    """Tipos documentais na ordem da configuração (sem 'desconhecido')."""
    return actions.listar_tipos()
