from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from app.routers.comum import DataHora
from app.routers.organizacoes import validations

IdBanco = Annotated[int, Field(ge=1, le=validations.ID_MAX)]


class NovoTomador(BaseModel):
    nome: str
    cnpj: str | None = None

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        return validations.validar_nome(v)

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str | None) -> str | None:
        return validations.normalizar_cnpj_opcional(v)


class NovoPrestador(BaseModel):
    cnpj: str
    razao_social: str

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        return validations.normalizar_cnpj(v)

    @field_validator("razao_social")
    @classmethod
    def _razao_social(cls, v: str) -> str:
        return validations.validar_nome(v, "razao_social")


class NovoContrato(BaseModel):
    tomador_id: IdBanco
    prestador_id: IdBanco
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None

    @model_validator(mode="after")
    def _vigencia(self):
        if self.vigencia_inicio and self.vigencia_fim and self.vigencia_fim < self.vigencia_inicio:
            raise ValueError("vigencia_fim não pode ser anterior a vigencia_inicio")
        return self


class AtivoIn(BaseModel):
    ativo: StrictBool


class TomadorOut(BaseModel):
    id: int
    nome: str
    cnpj: str | None
    ativo: bool
    criado_em: DataHora


class PrestadorOut(BaseModel):
    id: int
    cnpj: str
    razao_social: str
    ativo: bool
    criado_em: DataHora


class ContratoOut(BaseModel):
    id: int
    tomador_id: int
    prestador_id: int
    ativo: bool
    vigencia_inicio: date | None
    vigencia_fim: date | None
    criado_em: DataHora
    perfil_jornada: str  # perfil de jornada usado na análise de ponto dos lotes do contrato
    tomador_nome: str
    tomador_ativo: bool
    prestador_razao_social: str
    prestador_cnpj: str
    prestador_ativo: bool
    acesso_prestador: Literal["ativo", "convite_pendente", "sem_acesso"]  # usuário ativo / convite pendente / nada
