from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.routers.comum import DataHora
from app.routers.documentos import validations


class AtualizacaoCampos(BaseModel):
    campos: dict[str, str | None]
    revisor: str | None = None  # IGNORADO: o autor gravado é o e-mail do usuário autenticado

    @field_validator("campos")
    @classmethod
    def _campos_validos(cls, v: dict) -> dict:
        return validations.validar_campos(v)


class ExtrasDocumentoOut(BaseModel):
    """Campos aditivos comuns às respostas de documento (CPF, RG e PIS saem mascarados)."""
    campos: dict[str, str]
    pessoa: str | None  # campo 'nome' extraído
    nome_arquivo: str
    nome_original: str | None = None
    n_paginas: int
    processado_em: DataHora  # criação do lote


class PaginaOut(BaseModel):
    numero: int
    imagem_url: str
    texto: str | None


class DocumentoOut(ExtrasDocumentoOut):
    id: int
    lote_id: int
    ordem: int
    pagina_ini: int
    pagina_fim: int
    estado: str
    tipo: str | None
    confianca: float | None
    segmentacao_ambigua: bool
    tipo_original: str | None
    revisor: str | None
    revisado_em: DataHora | None
    motivo_revisao: str | None
    probabilidades: dict[str, float] | None
    modelo: str | None = None  # modelo que classificou (Jev, regras...)
    versao_prompt: str | None = None
    segunda_opiniao: dict[str, Any] | None = None  # Gemini: {modelo, versao_prompt, tipo, status}
    paginas: list[PaginaOut]


class DocumentoListadoOut(ExtrasDocumentoOut):
    id: int
    lote_id: int
    ordem: int
    pagina_ini: int
    pagina_fim: int
    estado: str
    tipo: str | None
    confianca: float | None
    contrato_id: int | None


class GrupoDocumentosOut(BaseModel):
    tipo: str  # slug, 'desconhecido' ou 'sem_tipo'
    total: int
    documentos: list[DocumentoListadoOut]


class DocumentosAgrupadosOut(BaseModel):
    grupos: list[GrupoDocumentosOut]


# ---- análise de folha de ponto (Goal 6). Apoio à auditoria, não parecer jurídico.
# Devolvida com response_model_exclude_unset=True: documento ainda sem linha em analise_ponto
# responde só {documento_id, estado: "pendente"}.

class VigenciaParametroOut(BaseModel):
    desde: str  # AAAA-MM-DD: o valor vale a partir desta data
    valor: float
    base_legal: str


class ParametroPerfilOut(BaseModel):
    valor: float  # valor de base (antes da primeira vigência)
    base_legal: str
    vigencias: list[VigenciaParametroOut] | None = None  # ausente em análises anteriores à vigência por data


class DivergenciaPontoOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    tipo: str
    data: str | None = None
    minutos: float | None = None
    base_legal: str | None = None
    detalhe: str | None = None
    campo: str | None = None  # só nas divergências de total declarado
    campos_ausentes: list[str] | None = None  # só em espelho_incompleto


class DiferencaGeminiOut(BaseModel):
    tipo: str | None
    data: str | None
    campo: str | None
    minutos_codigo: float | None
    minutos_gemini: float | None
    motivo: str  # so_codigo | so_gemini | minutos_diferentes


class ToleranciaPorMarcacaoOut(BaseModel):
    aplicada: bool
    dias_com_horario_previsto: int
    dias_sem_horario_previsto: int
    motivo_nao_aplicada: str | None


class TotaisDeclaradosOut(BaseModel):
    comparado: bool
    total_horas_min: float | None = None
    horas_extras_min: float | None = None
    extras_bruto_min: float | None = None
    extras_min_com_tolerancia: float | None = None
    extras_declarado_igual_ao_bruto: bool | None = None
    extras_declarado_igual_ao_com_tolerancia: bool | None = None


class ResumoTotaisPontoOut(BaseModel):
    trabalhado_min: float
    jornada_computada_min: float | None = None  # com a hora noturna reduzida; ausente em análises antigas
    extras_min: float
    extras_bruto_min: float
    noturno_real_min: float
    noturno_computado_min: float
    prorrogacao_noturna_min: float | None = None  # CLT art. 73, § 5º; ausente em análises antigas
    prorrogacao_noturna_computada_min: float | None = None
    dias_validos: int
    dias_invalidos: int


class DiaPontoOut(BaseModel):
    model_config = ConfigDict(extra="allow")  # campos novos da apuração passam sem perda
    data: str
    pares: list[Any] | None = None  # ausente nas linhas gravadas (a apuração não persiste as marcações brutas por dia)
    trabalhado_min: float
    extras_min: float
    extras_bruto_min: float | None = None
    intervalo_min: float | None = None
    noturno_real_min: float | None = None
    noturno_computado_min: float | None = None


class TotaisPontoOut(BaseModel):
    dias: list[DiaPontoOut]
    totais: ResumoTotaisPontoOut
    intervalo_pre_assinalado: bool
    intervalos_nao_verificados: list[Any]
    semanas_avaliadas_descanso: int
    # por semana: inicio, regra_vigente_em (domingo), jornada_computada_min, limite_semanal_min, dias_informados
    semanas: list[dict[str, Any]] | None = None
    # Portaria MTP 671/2021, art. 84: tipo_registro, situacao (completo | incompleto | nao_aplicavel |
    # nao_verificado), campos_ausentes e campos_nao_lidos; ausente em análises antigas
    espelho: dict[str, Any] | None = None
    tolerancia_por_marcacao: ToleranciaPorMarcacaoOut
    horario_contratual: list[Any]
    declarados: TotaisDeclaradosOut


class PontoBritanicoOut(BaseModel):
    conclusivo: bool
    sinal_risco: bool | None  # sinal de risco, não prova de fraude
    dias: int
    fracao_uniforme: float | None


class ScoreDimensaoOut(BaseModel):
    """Uma dimensão de risco. Dimensão avaliada: score, confianca, n_niveis e probabilidades vêm do Jev.
    Indeterminada (confiança baixa): normalizado nulo. Não avaliada (sem dados, ex.: descanso sem semana
    completa): nao_avaliada=True, motivo preenchido e os campos do Jev nulos. Linhas gravadas antes do campo
    `nao_avaliada` não o trazem (ausente)."""
    score: float | None = None  # nível escolhido pelo Jev
    confianca: float | None = None
    n_niveis: int | None = None
    probabilidades: dict[str, float] | None = None
    normalizado: float | None = None  # None se indeterminada ou não avaliada
    indeterminada: bool
    nao_avaliada: bool | None = None
    motivo: str | None = None  # só quando nao_avaliada


class ContagemHorasExtrasOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    dias_analisados: int | None = None
    dias_acima_do_limite_diario: int | None = None
    fracao_dos_dias_acima_do_limite: float | None = None
    maior_excesso_diario_min: float | None = None
    semanas_acima_de_44h: int | None = None  # nome antigo (análises anteriores à vigência por data)
    semanas_acima_do_limite_semanal: int | None = None
    total_horas_extras_min: float | None = None


class ContagemIntervalosOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    dias_analisados: int | None = None
    dias_com_intervalo_intrajornada_insuficiente: int | None = None
    maior_falta_de_intervalo_min: float | None = None
    dias_com_falta_de_intervalo_pequena: int | None = None
    dias_com_falta_de_intervalo_maior: int | None = None
    limite_da_falta_pequena_min: float | None = None
    dias_com_interjornada_menor_que_11h: int | None = None
    maior_falta_de_interjornada_min: float | None = None
    dias_com_intervalo_nao_verificado: int | None = None


class ContagemDescansoOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    semanas_completas_avaliadas: int | None = None
    semanas_sem_descanso_de_24h: int | None = None  # nome antigo
    semanas_sem_descanso_semanal: int | None = None
    maior_falta_de_descanso_min: float | None = None


class ContagemRegistroOut(BaseModel):
    model_config = ConfigDict(extra="allow")
    dias_com_marcacao_valida: int | None = None
    dias_com_marcacao_invalida: int | None = None
    ponto_britanico: str | None = None  # inconclusivo | sinal_de_ponto_britanico | sem_sinal
    fracao_de_dias_com_horario_uniforme: float | None = None
    totais_declarados_informados: bool | None = None
    totais_declarados_divergentes: int | None = None
    maior_diferenca_do_total_declarado_min: float | None = None
    campos_obrigatorios_do_espelho: int | None = None
    campos_do_espelho_ausentes: int | None = None


class ContagensPontoOut(BaseModel):
    """Contagens por dimensão (calculadas em código, base do julgamento do Jev). `nao_avaliadas` é a LISTA de
    dimensões sem dados para avaliar (chave ausente em linhas anteriores ao PR #45)."""
    model_config = ConfigDict(extra="allow")
    horas_extras: ContagemHorasExtrasOut | None = None
    intervalos: ContagemIntervalosOut | None = None
    descanso: ContagemDescansoOut | None = None
    registro: ContagemRegistroOut | None = None
    nao_avaliadas: list[str] | None = None


class AnalisePontoOut(BaseModel):
    documento_id: int
    estado: str  # pendente | concluida | erro
    erro: str | None = None
    perfil_nome: str | None = None  # perfil do contrato do lote; ausente em análises antigas (clt_padrao)
    perfil_nome_legivel: str | None = None  # nome do perfil gravado ("Padrão", nome da convenção); null a quem não o vê
    perfil: dict[str, ParametroPerfilOut] | None = None  # perfil efetivo usado (próprios + herdados)
    marcacoes: list[dict[str, Any]] | None = None  # como extraídas pelo Gemini: {data, pares: [[entrada, saida]...]}
    intervalo_pre_assinalado: bool | None = None
    totais: TotaisPontoOut | None = None
    divergencias: list[DivergenciaPontoOut] | None = None
    diferencas_gemini: list[DiferencaGeminiOut] | None = None
    ponto_britanico: PontoBritanicoOut | None = None
    analise: str | None = None
    contagens: ContagensPontoOut | None = None
    scores_dimensao: dict[str, ScoreDimensaoOut] | None = None
    score_geral: float | None = None  # máximo das dimensões (0 a 1)
    requer_revisao: bool | None = None
    modelo_gemini: str | None = None
    modelo_jev: str | None = None
    versao_prompt_gemini: str | None = None
    versao_prompt_jev: str | None = None
    custo: dict[str, Any] | None = None
    atualizado_em: DataHora | None = None
