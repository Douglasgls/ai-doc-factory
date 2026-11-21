from pydantic import BaseModel, field_validator

from app.routers.comum import DataHora
from app.routers.documentos.schemas import ExtrasDocumentoOut
from app.routers.revisao import validations


class Revisao(BaseModel):
    tipo: str
    revisor: str | None = None  # IGNORADO: o revisor gravado é o e-mail do usuário autenticado

    @field_validator("tipo")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        return validations.validar_tipo(v)


class ItemFilaRevisaoOut(ExtrasDocumentoOut):
    id: int
    lote_id: int
    tipo_sugerido: str | None
    confianca: float | None
    motivo: str | None
    imagem_url: str  # primeira página do documento
    pagina_ini: int
    pagina_fim: int


class RevisaoOut(BaseModel):
    id: int
    estado: str
    tipo: str
    tipo_original: str | None
    revisor: str
    revisado_em: DataHora
