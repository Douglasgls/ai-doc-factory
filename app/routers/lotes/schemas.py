from pydantic import BaseModel


class LoteCriadoOut(BaseModel):
    lote_id: int
    estado: str
    existente: bool  # True quando o mesmo arquivo (sha256) já tinha sido enviado
    empresa_id: int | None


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
