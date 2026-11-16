import math
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator, model_validator

from app.routers.documentos.schemas import ParametroPerfilOut

# Nome do perfil: minúsculas, dígitos e sublinhado (vai no caminho da URL e em contrato.perfil_jornada).
NomePerfil = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,50}$")]
BASE_LEGAL_MAX = 300


class ParametroProprio(BaseModel):
    parametro: str
    valor: float
    base_legal: str
    vigente_desde: date | None = None  # None = valor de base do parâmetro neste perfil

    @field_validator("valor")
    @classmethod
    def _valor(cls, v: float) -> float:
        if not math.isfinite(v) or v < 0:
            raise ValueError("valor deve ser um número finito maior ou igual a zero")
        return v

    @field_validator("base_legal")
    @classmethod
    def _base_legal(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > BASE_LEGAL_MAX:
            raise ValueError(f"base_legal é obrigatória (até {BASE_LEGAL_MAX} caracteres)")
        return v


class PerfilEntrada(BaseModel):
    """Só os parâmetros que diferem de `clt_padrao`. Um parâmetro informado substitui a linha do tempo INTEIRA do
    parâmetro (inclusive as vigências do padrão) e por isso precisa do valor de base (`vigente_desde` nulo)."""
    parametros: list[ParametroProprio] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _coerencia(self):
        chaves = [(p.parametro, p.vigente_desde) for p in self.parametros]
        if len(set(chaves)) != len(chaves):
            raise ValueError("parâmetro repetido com a mesma vigente_desde")
        sem_base = sorted({p.parametro for p in self.parametros} - {p for p, d in chaves if d is None})
        if sem_base:
            raise ValueError(f"parâmetro sem valor de base (vigente_desde nulo): {', '.join(sem_base)}")
        return self


class ParametroProprioOut(BaseModel):
    parametro: str
    valor: float
    unidade: str
    base_legal: str
    vigente_desde: date | None


class PerfilResumoOut(BaseModel):
    perfil: str
    padrao: bool
    parametros_proprios: int  # parâmetros distintos que o perfil guarda
    contratos: int  # contratos que apontam para o perfil


class PerfilOut(BaseModel):
    perfil: str
    padrao: bool
    proprios: list[ParametroProprioOut]  # o que o perfil guarda
    efetivo: dict[str, ParametroPerfilOut]  # o que a análise usa: próprios + herdados de clt_padrao


class AssociacaoPerfil(BaseModel):
    perfil: NomePerfil
