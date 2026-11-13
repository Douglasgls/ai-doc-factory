from fastapi import APIRouter, Response

from app.routers.documentos import actions
from app.routers.documentos.schemas import (
    AnalisePontoOut, AtualizacaoCampos, DocumentoOut, DocumentosAgrupadosOut)
from app.routers.revisao.schemas import Revisao

router = APIRouter(tags=["Documentos"])


@router.get("/documentos", response_model=DocumentosAgrupadosOut)
def listar_documentos(empresa_id: int | None = None, falhou: bool | None = None):
    """Agrupados por tipo. `falhou=true` só estado 'erro'; `false` exclui; omitido não filtra."""
    return actions.listar_documentos(empresa_id, falhou)


@router.patch("/documentos/{documento_id}/tipo", response_model=DocumentoOut)
def atualizar_tipo(documento_id: int, corpo: Revisao):
    """Corrige o tipo (documento fora de 'segmentado' e 'erro'); vira 'revisado'."""
    return actions.atualizar_tipo(documento_id, corpo)


@router.put("/documentos/{documento_id}/campos", response_model=DocumentoOut)
def atualizar_campos(documento_id: int, corpo: AtualizacaoCampos):
    """Corrige campos extraídos: string não vazia grava com origem 'humano'; null remove. Devolve o documento."""
    return actions.atualizar_campos(documento_id, corpo)


@router.delete("/documentos/{documento_id}", status_code=204)
def excluir_documento(documento_id: int):
    """Apaga só a linha do documento; análise e campos caem em cascata; páginas ficam com documento_id NULL.
    409 se o lote está em andamento."""
    actions.excluir_documento(documento_id)
    return Response(status_code=204)


@router.get("/documentos/{documento_id}", response_model=DocumentoOut)
def obter_documento(documento_id: int):
    return actions.obter_documento(documento_id)


@router.get("/documentos/{documento_id}/analise-ponto", response_model=AnalisePontoOut, response_model_exclude_unset=True)
def analise_ponto(documento_id: int):
    """Apoio à auditoria, não parecer jurídico; convenção coletiva e acordo de compensação podem alterar os limites."""
    return actions.obter_analise_ponto(documento_id)
