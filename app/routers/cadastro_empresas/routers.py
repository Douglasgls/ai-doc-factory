from fastapi import APIRouter

from app.routers.cadastro_empresas import actions
from app.routers.cadastro_empresas.schemas import EmpresaOut, NovaEmpresa

router = APIRouter(tags=["Cadastro de empresas"])


@router.post("/cadastro-empresas", status_code=201, response_model=EmpresaOut)
def criar_empresa(corpo: NovaEmpresa):
    return actions.criar_empresa(corpo.nome)


@router.get("/cadastro-empresas", response_model=list[EmpresaOut])
def listar_empresas():
    return actions.listar_empresas()


@router.get("/cadastro-empresas/{empresa_id}", response_model=EmpresaOut)
def obter_empresa(empresa_id: int):
    return actions.obter_empresa(empresa_id)
