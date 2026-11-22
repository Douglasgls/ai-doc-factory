from typing import Literal

from pydantic import BaseModel, field_validator

from app.routers.convites.schemas import validar_email
from app.routers.organizacoes import validations
from app.routers.terceirizadas.schemas import ConviteTerceirizadaOut


class NovaEmpresaPropria(BaseModel):
    cnpj: str
    razao_social: str
    email_admin: str  # de quem receberá o convite de administrador (se a empresa ainda não tiver acesso)

    @field_validator("cnpj")
    @classmethod
    def _cnpj(cls, v: str) -> str:
        return validations.normalizar_cnpj(v)

    @field_validator("razao_social")
    @classmethod
    def _razao_social(cls, v: str) -> str:
        return validations.validar_nome(v, "razao_social")

    @field_validator("email_admin")
    @classmethod
    def _email(cls, v: str) -> str:
        return validar_email(v)


class ContratoProprioOut(BaseModel):
    id: int
    ativo: bool
    proprio: bool


class OrganizacaoCriadaOut(BaseModel):
    id: int
    cnpj: str
    nome: str  # o nome já cadastrado, quando o CNPJ existia


class EmpresaPropriaOut(BaseModel):
    contrato: ContratoProprioOut
    tomador: OrganizacaoCriadaOut
    prestador: OrganizacaoCriadaOut
    acesso: Literal["convite_criado", "convite_pendente", "ja_tem_acesso"]
    convite: ConviteTerceirizadaOut | None = None  # o token só aparece nesta resposta
