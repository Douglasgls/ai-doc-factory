from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.routers.organizacoes.schemas import ContratoOut, IdBanco
from app.routers.perfis_jornada import actions
from app.routers.perfis_jornada.schemas import AssociacaoPerfil, NomePerfil, PerfilEntrada, PerfilOut, PerfilResumoOut

router = APIRouter(tags=["Perfis de jornada"])  # só plataforma (api.py)


@router.get("/perfis-jornada", response_model=list[PerfilResumoOut])
def listar_perfis(session: Session = Depends(get_session)):
    return actions.listar_perfis(session)


# exclude_unset: parâmetro sem vigências sai sem a chave `vigencias`, como em GET /documentos/{id}/analise-ponto
@router.get("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True)
def obter_perfil(perfil: NomePerfil, session: Session = Depends(get_session)):
    """`proprios`: o que o perfil guarda. `efetivo`: o que a análise usa (próprios + herdados de `clt_padrao`)."""
    return actions.obter_perfil(session, perfil)


@router.put("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True)
def gravar_perfil(perfil: NomePerfil, corpo: PerfilEntrada, session: Session = Depends(get_session)):
    """Cria o perfil ou substitui todos os seus parâmetros próprios. Informe só o que difere de `clt_padrao`."""
    return actions.gravar_perfil(session, perfil, corpo)


@router.put("/contratos/{contrato_id}/perfil-jornada", response_model=ContratoOut)
def associar_perfil(contrato_id: IdBanco, corpo: AssociacaoPerfil, session: Session = Depends(get_session)):
    return actions.associar_perfil(session, contrato_id, corpo.perfil)
