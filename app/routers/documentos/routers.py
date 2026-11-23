from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.database import get_session
from app.downloads import content_disposition

from app.escopo import documento_para_escrita, documento_para_leitura
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from app.routers.documentos import actions
from app.routers.documentos.schemas import (
    AnalisePontoOut, AtualizacaoCampos, DocumentoOut, DocumentosAgrupadosOut)
from app.routers.organizacoes.schemas import IdBanco
from app.routers.revisao.schemas import Revisao

router = APIRouter(tags=["Documentos"])


@router.get("/documentos", response_model=DocumentosAgrupadosOut)
def listar_documentos(contrato_id: Annotated[IdBanco | None, Query()] = None, falhou: bool | None = None,
                      usuario: UsuarioContexto = Depends(exigir_usuario), session: Session = Depends(get_session)):
    """Agrupados por tipo. `contrato_id` filtra pelo contrato do lote (404 se não existe). `falhou=true` só estado
    'erro'; `false` exclui; omitido não filtra."""
    return actions.listar_documentos(session, contrato_id, falhou, usuario=usuario)


@router.patch("/documentos/{documento_id}/tipo", response_model=DocumentoOut,
              dependencies=[Depends(documento_para_escrita)])
def atualizar_tipo(documento_id: int, corpo: Revisao, usuario: UsuarioContexto = Depends(exigir_usuario),
                   session: Session = Depends(get_session)):
    """Corrige o tipo (documento fora de 'segmentado' e 'erro'); vira 'revisado'."""
    return actions.atualizar_tipo(session, documento_id, corpo, usuario.email)


@router.put("/documentos/{documento_id}/campos", response_model=DocumentoOut,
            dependencies=[Depends(documento_para_escrita)])
def atualizar_campos(documento_id: int, corpo: AtualizacaoCampos, usuario: UsuarioContexto = Depends(exigir_usuario),
                     session: Session = Depends(get_session)):
    """Corrige campos extraídos: string não vazia grava com origem 'humano'; null remove. Devolve o documento."""
    return actions.atualizar_campos(session, documento_id, corpo, usuario.email)


@router.delete("/documentos/{documento_id}", status_code=204, dependencies=[Depends(documento_para_escrita)])
def excluir_documento(documento_id: int, session: Session = Depends(get_session)):
    """Apaga só a linha do documento; análise e campos caem em cascata; páginas ficam com documento_id NULL.
    409 se o lote está em andamento."""
    actions.excluir_documento(session, documento_id)
    return Response(status_code=204)


@router.get("/documentos/{documento_id}", response_model=DocumentoOut,
            dependencies=[Depends(documento_para_leitura)])
def obter_documento(documento_id: int, session: Session = Depends(get_session)):
    return actions.obter_documento(session, documento_id)


@router.get("/documentos/{documento_id}/analise-ponto", response_model=AnalisePontoOut,
            response_model_exclude_unset=True, dependencies=[Depends(documento_para_leitura)])
def analise_ponto(documento_id: int, usuario: UsuarioContexto = Depends(exigir_usuario),
                  session: Session = Depends(get_session)):
    """Apoio à auditoria, não parecer jurídico; convenção coletiva e acordo de compensação podem alterar os limites."""
    return actions.obter_analise_ponto(session, documento_id, usuario)


@router.get("/documentos/{documento_id}/download", dependencies=[Depends(documento_para_leitura)])
def download_documento(documento_id: int, session: Session = Depends(get_session)):
    """Baixa o PDF recortado do documento com o nome padronizado."""
    pdf_bytes, nome_arquivo = actions.download_documento(session, documento_id)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(nome_arquivo)},
    )
