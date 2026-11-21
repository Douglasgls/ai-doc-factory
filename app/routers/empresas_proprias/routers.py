from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.routers.auth.actions import UsuarioContexto, exigir_plataforma
from app.routers.empresas_proprias import actions
from app.routers.empresas_proprias.schemas import EmpresaPropriaOut, NovaEmpresaPropria

router = APIRouter(tags=["Empresas próprias"])  # só plataforma (api.py)


@router.post("/empresas-proprias", status_code=201, response_model=EmpresaPropriaOut)
def cadastrar_empresa_propria(corpo: NovaEmpresaPropria, usuario: UsuarioContexto = Depends(exigir_plataforma),
                              session: Session = Depends(get_session)):
    """Cria (ou reutiliza, pelo CNPJ) o tomador e o prestador da empresa, o contrato próprio entre eles e o convite do
    administrador. O token do convite vem só nesta resposta."""
    return actions.cadastrar(session, corpo, usuario)
