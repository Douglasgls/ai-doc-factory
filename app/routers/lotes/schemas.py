from pydantic import BaseModel, ConfigDict


class LoteCriadoOut(BaseModel):
    lote_id: int
    estado: str
    existente: bool  # True quando o mesmo arquivo (sha256) já tinha sido enviado
    empresa_id: int | None
    reprocessando: bool | None = None  # só no reenvio de um lote em 'erro' (volta para 'recebido')


class EventoProgressoOut(BaseModel):
    """Evento de progresso do lote (Redis). Os extras variam por etapa; os que não vierem ficam ausentes."""
    model_config = ConfigDict(extra="allow")
    lote_id: int
    etapa: str
    mensagem: str
    timestamp: str  # ISO 8601 UTC
    pagina_atual: int | None = None
    total_paginas: int | None = None
    total_documentos: int | None = None
    docs_pendentes: int | None = None
    documento_id: int | None = None
    tipo: str | None = None
    estado_documento: str | None = None
    segmentacao_ambigua: bool | None = None


class DocumentoDoLoteOut(BaseModel):
    id: int
    ordem: int
    pagina_ini: int
    pagina_fim: int
    estado: str
    tipo: str | None
    confianca: float | None
    segmentacao_ambigua: bool
    probabilidades: dict[str, float] | None
    tipo_original: str | None


class LoteOut(BaseModel):
    id: int
    nome_arquivo: str
    estado: str
    docs_pendentes: int
    empresa_id: int | None
    documentos: list[DocumentoDoLoteOut]
    ultimo_evento: EventoProgressoOut | None = None  # None sem eventos no Redis (TTL ou lote antigo)
    historico_eventos: list[EventoProgressoOut] = []
