from pydantic import BaseModel


# Os modelos abaixo são devolvidos com response_model_exclude_unset=True: chaves condicionais
# (bons/ruins, campo, cpf, valores...) só aparecem quando o cálculo as produz.

class CriterioOut(BaseModel):
    peso: int
    peso_efetivo: float | None
    nota: float | None
    pendente: bool
    aplicavel: bool
    bons: int | None = None  # só nos critérios calculados
    ruins: int | None = None


class CriteriosOut(BaseModel):
    completude: CriterioOut
    validade: CriterioOut
    consistencia: CriterioOut


class ValorComparadoOut(BaseModel):
    documento: int
    tipo: str | None
    valor: str


class DescontoOut(BaseModel):
    criterio: str
    documento: int | None
    tipo: str | None
    regra: str
    detalhe: str
    pontos: float
    campo: str | None = None  # só em campo_divergente
    conferir: bool | None = None
    valores: list[ValorComparadoOut] | None = None
    cpf: str | None = None  # mascarado; só em divergência entre documentos do mesmo CPF


class PendenciaOut(BaseModel):
    criterio: str
    documento: int | None
    tipo: str | None
    motivo: str


class NivelConformidadeOut(BaseModel):
    """Resultado de um nível (geral, por tipo ou por documento). score/classificacao nulos = nada analisável."""
    score: int | None
    score_bruto: float | None
    classificacao: str | None
    provisorio: bool
    criterios: CriteriosOut
    descontos: list[DescontoOut]
    pendencias: list[PendenciaOut]


class EmpresaResumoOut(BaseModel):
    cnpj: str
    razao_social: str | None
    documentos_por_tipo: dict[str, int]
    score: int | None
    classificacao: str | None
    provisorio: bool


class ConformidadeEmpresaOut(BaseModel):
    cnpj: str
    razao_social: str | None
    documentos_por_tipo: dict[str, int]
    data_referencia: str  # ISO, data usada para a validade
    geral: NivelConformidadeOut
    por_tipo: dict[str, NivelConformidadeOut]
    por_documento: dict[int, NivelConformidadeOut]  # chave: id do documento


class EmpresaDoLoteOut(EmpresaResumoOut):
    documentos: list[int]  # ids dos documentos da empresa neste lote


class SemEmpresaOut(BaseModel):
    documento: int
    tipo: str | None
    estado: str
    motivo: str


class ConformidadeLoteOut(BaseModel):
    lote_id: int
    empresas: list[EmpresaDoLoteOut]
    sem_empresa: list[SemEmpresaOut]
