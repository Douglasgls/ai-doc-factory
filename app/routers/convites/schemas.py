import re
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

from app import senhas
from app.routers.comum import DataHora
from app.routers.organizacoes import validations
from app.routers.organizacoes.schemas import IdBanco

EMAIL_MAX = 254
_FORMATO_EMAIL = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+([.-][a-zA-Z0-9]+)*\.[a-zA-Z]{2,}$")
SENHA_MIN = 8
Nivel = Literal["plataforma", "tomador", "prestador"]  # espelha config.NIVEIS_ACESSO (CHECK do banco)
Papel = Literal["admin", "membro"]  # espelha config.PAPEIS


def validar_email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > EMAIL_MAX or not _FORMATO_EMAIL.match(v):
        raise ValueError("e-mail inválido")
    return v


class NovoConvite(BaseModel):
    email: str
    nivel: Nivel
    papel: Papel
    tomador_id: IdBanco | None = None
    prestador_id: IdBanco | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return validar_email(v)

    @model_validator(mode="after")
    def _vinculo(self):
        esperado = {"plataforma": (False, False), "tomador": (True, False), "prestador": (False, True)}[self.nivel]
        if (self.tomador_id is not None, self.prestador_id is not None) != esperado:
            raise ValueError({"plataforma": "nível plataforma não tem organização",
                              "tomador": "nível tomador exige tomador_id (e só ele)",
                              "prestador": "nível prestador exige prestador_id (e só ele)"}[self.nivel])
        return self


class ConviteCriadoOut(BaseModel):
    id: int
    email: str
    nivel: str
    papel: str
    expira_em: DataHora
    token: str  # só aparece nesta resposta


class ConviteOut(BaseModel):
    id: int
    email: str
    nivel: str
    papel: str
    tomador_id: int | None
    prestador_id: int | None
    organizacao_nome: str | None
    estado: Literal["pendente", "usado", "expirado"]
    criado_por: int | None
    criado_em: DataHora
    expira_em: DataHora
    usado_em: DataHora | None
    usuario_id: int | None


class ConvitePublicoOut(BaseModel):
    email: str
    nivel: str
    organizacao_nome: str | None
    expira_em: DataHora


class AceiteIn(BaseModel):
    nome: str
    senha: str

    @field_validator("nome")
    @classmethod
    def _nome(cls, v: str) -> str:
        return validations.validar_nome(v)

    @field_validator("senha")
    @classmethod
    def _senha(cls, v: str) -> str:
        if len(v) < SENHA_MIN:
            raise ValueError(f"senha deve ter ao menos {SENHA_MIN} caracteres")
        if not senhas.senha_valida_tamanho(v):
            raise ValueError(f"senha acima do limite de {senhas.SENHA_MAX_BYTES} bytes")
        return v
