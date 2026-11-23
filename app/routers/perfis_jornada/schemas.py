import math
from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator

from app.routers.documentos.schemas import ParametroPerfilOut
from app.routers.organizacoes.schemas import IdBanco

# Nome do perfil: minúsculas, dígitos e sublinhado (vai no caminho da URL e em contrato.perfil_jornada).
NomePerfil = Annotated[str, Field(pattern=r"^[a-z0-9_]{1,50}$")]
BASE_LEGAL_MAX = 300
NOME_MAX = 100
SINDICATO_MAX = 200


def _texto(v: str | None, maximo: int, campo: str, obrigatorio: bool) -> str | None:
    if v is None:
        if obrigatorio:
            raise ValueError(f"{campo} é obrigatório")
        return None
    v = v.strip()
    if not v and obrigatorio:
        raise ValueError(f"{campo} é obrigatório")
    if len(v) > maximo:
        raise ValueError(f"{campo} deve ter até {maximo} caracteres")
    return v or None


def vigencia_coerente(inicio: date | None, fim: date | None) -> None:
    if inicio is not None and fim is not None and fim < inicio:
        raise ValueError("vigencia_fim deve ser maior ou igual a vigencia_inicio")


class CadastroEntrada(BaseModel):
    """Nome, sindicato e vigência de um perfil. Em edição, campo ausente = não muda; `null` limpa sindicato e vigência.
    `geral` e `prestador_id` (dono) só a plataforma envia; de um admin de empresa própria, qualquer um dos dois dá 403."""
    nome: str | None = None
    sindicato: str | None = None
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    geral: StrictBool | None = None  # visível a todos que leem perfis; exclusivo com dono; `null` dá 422
    prestador_id: IdBanco | None = None  # dono; em edição, `null` tira o dono

    @field_validator("nome")
    @classmethod
    def _nome(cls, v):
        return None if v is None else _texto(v, NOME_MAX, "nome", True)

    @field_validator("sindicato")
    @classmethod
    def _sindicato(cls, v):
        return _texto(v, SINDICATO_MAX, "sindicato", False)

    @model_validator(mode="after")
    def _vigencia(self):
        vigencia_coerente(self.vigencia_inicio, self.vigencia_fim)
        return self

    @model_validator(mode="after")
    def _escopo(self):
        if "geral" in self.model_fields_set and self.geral is None:
            raise ValueError("geral não pode ser nulo")
        if self.geral and self.prestador_id is not None:
            raise ValueError("perfil geral não tem dono: não envie geral=true junto com prestador_id")
        return self


class PerfilNovo(CadastroEntrada):
    """POST /perfis-jornada: o slug é gerado pelo servidor a partir do nome."""
    nome: str


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


class PerfilEntrada(CadastroEntrada):
    """Só os parâmetros que diferem de `clt_padrao`. Um parâmetro informado substitui a linha do tempo INTEIRA do
    parâmetro (inclusive as vigências do padrão) e por isso precisa do valor de base (`vigente_desde` nulo).
    `parametros` ausente = não mexe nos parâmetros (só no cadastro); obrigatório para criar o perfil por PUT."""
    parametros: list[ParametroProprio] | None = Field(default=None, min_length=1, max_length=200)

    @model_validator(mode="after")
    def _coerencia(self):
        if self.parametros is None:
            return self
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


class CadastroOut(BaseModel):
    nome: str
    sindicato: str | None
    vigencia_inicio: date | None
    vigencia_fim: date | None
    vigente: bool  # hoje está dentro da vigência (início e fim vazios = sempre vigente)
    geral: bool  # visível a todos que leem perfis (o Padrão não usa)
    prestador_id: int | None  # dono; só a plataforma e o próprio dono o veem (os outros recebem null)
    editavel: bool  # o usuário que consulta pode editar o perfil (o Padrão nunca)


class PerfilResumoOut(CadastroOut):
    perfil: str
    padrao: bool
    parametros_proprios: int  # parâmetros distintos que o perfil guarda
    contratos: int  # contratos que apontam para o perfil


class PerfilOut(CadastroOut):
    perfil: str
    padrao: bool
    proprios: list[ParametroProprioOut]  # o que o perfil guarda
    efetivo: dict[str, ParametroPerfilOut]  # o que a análise usa: próprios + herdados de clt_padrao


class AssociacaoPerfil(BaseModel):
    perfil: NomePerfil
