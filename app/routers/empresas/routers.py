from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.escopo import lote_para_leitura
from app.routers.auth.actions import UsuarioContexto, exigir_usuario

from app.routers.empresas import actions
from app.routers.empresas.schemas import ConformidadeEmpresaOut, ConformidadeLoteOut, EmpresaResumoOut

router = APIRouter(tags=["Conformidade"])


@router.get("/empresas", response_model=list[EmpresaResumoOut])
def listar_empresas(session: Session = Depends(get_session), usuario: UsuarioContexto = Depends(exigir_usuario)):
    """Empresas prestadoras (por CNPJ validado) com score geral e classificação."""
    return actions.listar_empresas(session, usuario)


@router.get("/empresas/{cnpj:path}/conformidade", response_model=ConformidadeEmpresaOut, response_model_exclude_unset=True)
def conformidade_empresa(cnpj: str, session: Session = Depends(get_session),
                         usuario: UsuarioContexto = Depends(exigir_usuario)):
    """Três níveis (geral, por tipo, por documento). Aceita o CNPJ com ou sem pontuação."""
    return actions.conformidade_empresa(session, usuario, cnpj)


@router.get("/lotes/{lote_id}/conformidade", response_model=ConformidadeLoteOut, dependencies=[Depends(lote_para_leitura)])
def conformidade_lote(lote_id: int, session: Session = Depends(get_session),
                      usuario: UsuarioContexto = Depends(exigir_usuario)):
    """Empresas encontradas no lote (com o score geral de cada uma) e documentos sem empresa."""
    return actions.conformidade_lote(session, usuario, lote_id)
