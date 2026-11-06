from pydantic import BaseModel, field_validator

from app.routers.cadastro_empresas import validations
from app.routers.comum import DataHora


class NovaEmpresa(BaseModel):
    nome: str

    @field_validator("nome")
    @classmethod
    def _nome_preenchido(cls, v: str) -> str:
        return validations.validar_nome(v)


class LoteDaEmpresaOut(BaseModel):
    id: int
    nome_arquivo: str
    estado: str


class DocumentoDaEmpresaOut(BaseModel):
    id: int
    lote_id: int
    ordem: int
    pagina_ini: int
    pagina_fim: int
    tipo: str | None
    estado: str


class EmpresaOut(BaseModel):
    id: int
    nome: str
    criado_em: DataHora
    lotes: list[LoteDaEmpresaOut]
    documentos: list[DocumentoDaEmpresaOut]
    n_lotes: int
    n_documentos: int
