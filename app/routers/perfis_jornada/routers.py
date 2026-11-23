from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.escopo import leitura_de_perfis, perfil_de_contrato_proprio
from app.routers.auth.actions import UsuarioContexto
from app.routers.organizacoes.schemas import ContratoOut, IdBanco
from app.routers.perfis_jornada import actions
from app.routers.perfis_jornada.schemas import AssociacaoPerfil, NomePerfil, PerfilEntrada, PerfilNovo, PerfilOut, PerfilResumoOut

router = APIRouter(tags=["Perfis de jornada"])  # só plataforma (api.py): criar/substituir perfil
# Plataforma e admin de empresa própria (decidido em app/escopo.py): ler perfis e escolher o do próprio contrato.
router_empresa_propria = APIRouter(tags=["Perfis de jornada"])


@router_empresa_propria.get("/perfis-jornada", response_model=list[PerfilResumoOut])
def listar_perfis(usuario: UsuarioContexto = Depends(leitura_de_perfis), session: Session = Depends(get_session)):
    """`contratos`: quantos contratos usam o perfil, dentro do escopo do usuário (todos, para a plataforma)."""
    return actions.listar_perfis(session, usuario)


# exclude_unset: parâmetro sem vigências sai sem a chave `vigencias`, como em GET /documentos/{id}/analise-ponto
@router_empresa_propria.get("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True,
                            dependencies=[Depends(leitura_de_perfis)])
def obter_perfil(perfil: NomePerfil, session: Session = Depends(get_session)):
    """`proprios`: o que o perfil guarda. `efetivo`: o que a análise usa (próprios + herdados de `clt_padrao`)."""
    return actions.obter_perfil(session, perfil)


@router.post("/perfis-jornada", response_model=PerfilOut, response_model_exclude_unset=True, status_code=201)
def criar_perfil(corpo: PerfilNovo, session: Session = Depends(get_session)):
    """Cria um perfil a partir do nome (sindicato e vigência opcionais); o slug é gerado pelo servidor. O perfil nasce
    sem parâmetros próprios (herda de `clt_padrao`); use o PUT para informá-los."""
    return actions.criar_perfil(session, corpo)


@router.put("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True)
def gravar_perfil(perfil: NomePerfil, corpo: PerfilEntrada, session: Session = Depends(get_session)):
    """Cria o perfil ou substitui todos os seus parâmetros próprios. Informe só o que difere de `clt_padrao`.
    Nome, sindicato e vigência são opcionais: o que não vier não muda; sem `parametros`, edita só o cadastro."""
    return actions.gravar_perfil(session, perfil, corpo)


@router_empresa_propria.put("/contratos/{contrato_id}/perfil-jornada", response_model=ContratoOut)
def associar_perfil(contrato_id: IdBanco, corpo: AssociacaoPerfil, _: str = Depends(perfil_de_contrato_proprio),
                    session: Session = Depends(get_session)):
    return actions.associar_perfil(session, contrato_id, corpo.perfil)
