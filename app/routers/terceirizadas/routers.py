from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session

from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.terceirizadas import actions
from app.routers.terceirizadas.schemas import NovaTerceirizada, TerceirizadaOut

router = APIRouter(tags=["Terceirizadas"])  # autenticada (api.py); admin do tomador ou plataforma, decidido na action


@router.post("/terceirizadas", status_code=201, response_model=TerceirizadaOut)
def cadastrar_terceirizada(corpo: NovaTerceirizada, usuario: UsuarioContexto = Depends(exigir_usuario),
                           session: Session = Depends(get_session)):
    """Cria (ou reutiliza, pelo CNPJ) a terceirizada e o contrato ativo. O token do convite vem só nesta resposta."""
    return actions.cadastrar(session, corpo, usuario)
