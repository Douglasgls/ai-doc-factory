from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_session
from app.escopo import escrita_de_perfis, leitura_de_perfis, perfil_de_contrato_proprio
from app.routers.auth.actions import UsuarioContexto
from app.routers.organizacoes.schemas import ContratoOut, IdBanco
from app.routers.perfis_jornada import actions
from app.routers.perfis_jornada.schemas import AssociacaoPerfil, NomePerfil, PerfilEntrada, PerfilNovo, PerfilOut, PerfilResumoOut

# Plataforma e admin de empresa própria (decidido em app/escopo.py): ler, criar e editar perfis do seu escopo e
# escolher o do próprio contrato. Quais perfis cada um vê e edita também é decidido em app/escopo.py.
router_empresa_propria = APIRouter(tags=["Perfis de jornada"])


@router_empresa_propria.get("/perfis-jornada", response_model=list[PerfilResumoOut])
def listar_perfis(usuario: UsuarioContexto = Depends(leitura_de_perfis), session: Session = Depends(get_session)):
    """`contratos`: quantos contratos usam o perfil, dentro do escopo do usuário (todos, para a plataforma)."""
    return actions.listar_perfis(session, usuario)


# exclude_unset: parâmetro sem vigências sai sem a chave `vigencias`, como em GET /documentos/{id}/analise-ponto
@router_empresa_propria.get("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True)
def obter_perfil(perfil: NomePerfil, usuario: UsuarioContexto = Depends(leitura_de_perfis),
                 session: Session = Depends(get_session)):
    """`proprios`: o que o perfil guarda. `efetivo`: o que a análise usa (próprios + herdados de `clt_padrao`).
    Perfil fora do escopo do usuário: 404, igual a inexistente."""
    return actions.obter_perfil(session, perfil, usuario)


@router_empresa_propria.post("/perfis-jornada", response_model=PerfilOut, response_model_exclude_unset=True,
                             status_code=201)
def criar_perfil(corpo: PerfilNovo, usuario: UsuarioContexto = Depends(escrita_de_perfis),
                 session: Session = Depends(get_session)):
    """Cria um perfil a partir do nome (sindicato e vigência opcionais); o slug é gerado pelo servidor. O perfil nasce
    sem parâmetros próprios (herda de `clt_padrao`); use o PUT para informá-los. O admin de empresa própria cria
    perfis dele (nunca gerais); só a plataforma envia `geral` e `prestador_id`."""
    return actions.criar_perfil(session, corpo, usuario)


@router_empresa_propria.put("/perfis-jornada/{perfil}", response_model=PerfilOut, response_model_exclude_unset=True)
def gravar_perfil(perfil: NomePerfil, corpo: PerfilEntrada, usuario: UsuarioContexto = Depends(escrita_de_perfis),
                  session: Session = Depends(get_session)):
    """Cria o perfil ou substitui todos os seus parâmetros próprios. Informe só o que difere de `clt_padrao`.
    Nome, sindicato e vigência são opcionais: o que não vier não muda; sem `parametros`, edita só o cadastro.
    Admin de empresa própria: só os perfis dele (404 fora do escopo, 403 em perfil geral ou de outro dono)."""
    return actions.gravar_perfil(session, perfil, corpo, usuario)


@router_empresa_propria.put("/contratos/{contrato_id}/perfil-jornada", response_model=ContratoOut)
def associar_perfil(contrato_id: IdBanco, corpo: AssociacaoPerfil, _: str = Depends(perfil_de_contrato_proprio),
                    usuario: UsuarioContexto = Depends(leitura_de_perfis), session: Session = Depends(get_session)):
    return actions.associar_perfil(session, contrato_id, corpo.perfil, usuario)
