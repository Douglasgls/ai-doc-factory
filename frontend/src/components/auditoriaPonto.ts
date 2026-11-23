// Tipos e funções puras da tela de auditoria de folha de ponto.
// Formato real: GET /documentos/{id}/analise-ponto (app/routers/documentos/actions.py), com `totais`
// vindo de app/ponto.py::apurar_folha (sem `divergencias`) e `marcacoes` como extraído pelo Gemini.
// Os rótulos dos códigos (tipos, dimensões, campos) ficam em utils/rotulos.ts.
import {
  ROTULO_CAMPO_ESPELHO,
  ROTULO_DIMENSAO_PONTO,
  ROTULO_DIVERGENCIA,
  ROTULO_MOTIVO_NAO_AVALIADA,
  emFrase,
  rotulo,
} from '../utils/rotulos'

export type TipoDivergencia =
  | 'horas_extras_acima_limite'
  | 'semana_acima_limite'
  | 'intervalo_intrajornada_insuficiente'
  | 'interjornada_insuficiente'
  | 'descanso_semanal_ausente'
  | 'marcacao_invalida'
  | 'total_declarado_divergente'
  | 'espelho_incompleto'

export interface Divergencia {
  tipo: string
  /** AAAA-MM-DD; null em total_declarado_divergente. */
  data: string | null
  minutos: number | null
  base_legal: string
  detalhe: string
  campo?: string
  /** Só em espelho_incompleto: campos do art. 84 da Portaria MTP 671/2021 que não aparecem (códigos de CAMPOS_ESPELHO). */
  campos_ausentes?: string[]
}

export interface MarcacaoDia {
  data: string
  /** Pares [entrada, saída] como "HH:MM", "HH:MM+1" (dia seguinte) ou datetime ISO. */
  pares: [string, string][]
}

export interface DiaApurado {
  data: string
  trabalhado_min: number
  extras_min: number
  extras_bruto_min: number
  intervalo_min: number
}

export interface Totais {
  dias: DiaApurado[]
  declarados?: {
    total_horas_min: number | null
    horas_extras_min: number | null
    extras_bruto_min?: number
  }
}

export interface PontoBritanico {
  conclusivo: boolean
  sinal_risco: boolean | null
  fracao_uniforme: number | null
  dias?: number
}

export interface DiferencaGemini {
  tipo: string | null
  data: string | null
  /** Só nas diferenças de total declarado: total_horas ou horas_extras. */
  campo?: string | null
  /** Minutos que o sistema calculou; null quando o sistema não apontou essa divergência. */
  minutos_codigo?: number | null
  /** Minutos que a leitura da IA trouxe; null quando a IA não apontou. */
  minutos_gemini?: number | null
  /** so_codigo | so_gemini | minutos_diferentes */
  motivo: string
}

/** Um parâmetro do perfil de jornada gravado na análise (o que valia quando a folha foi analisada). */
export interface ParametroPerfilGravado {
  valor: number
  base_legal?: string
  vigencias?: { desde: string; valor: number; base_legal?: string }[] | null
}

export type DimensaoPonto = 'horas_extras' | 'intervalos' | 'descanso' | 'registro'

export interface ScoreDimensao {
  normalizado: number | null
  indeterminada: boolean
  /** true quando a dimensão nem foi perguntada ao Jev por falta de dados (ex.: sem semana completa). */
  nao_avaliada?: boolean
  motivo?: string | null
}

/** Rótulo curto de uma dimensão sem valor: não avaliada (falta de dados) é diferente de indeterminada (confiança baixa). */
export const rotuloSemValor = (dim: ScoreDimensao | undefined): string =>
  dim?.nao_avaliada
    ? dim.motivo && ROTULO_MOTIVO_NAO_AVALIADA[dim.motivo]
      ? `Não avaliado: ${emFrase(ROTULO_MOTIVO_NAO_AVALIADA[dim.motivo])}`
      : 'Não avaliado'
    : 'Indeterminada'

export interface AnalisePonto {
  documento_id: number
  /** pendente (ainda não rodou), concluida ou erro. */
  estado: 'pendente' | 'concluida' | 'erro'
  erro?: string | null
  marcacoes?: MarcacaoDia[] | null
  totais?: Totais | null
  divergencias?: Divergencia[] | null
  diferencas_gemini?: DiferencaGemini[] | null
  ponto_britanico?: PontoBritanico | null
  analise?: string | null
  scores_dimensao?: Partial<Record<DimensaoPonto, ScoreDimensao>> | null
  /** Risco de 0 a 1, em que maior é pior; null = indeterminado. */
  score_geral?: number | null
  requer_revisao?: boolean
  /** Perfil de jornada gravado na análise (identificador interno). */
  perfil_nome?: string | null
  /** Nome legível do perfil gravado; null quando quem vê não pode ver a convenção. */
  perfil_nome_legivel?: string | null
  /** Perfil efetivo usado na análise, como foi gravado. */
  perfil?: Record<string, ParametroPerfilGravado> | null
}

/** Faixas do risco em % (maior = pior): abaixo de `medio` é baixo, de `medio` a `alto - 1` é médio, `alto` ou mais é alto. */
export const FAIXAS_RISCO = { medio: 34, alto: 67 } as const

export type NivelRisco = 'baixo' | 'medio' | 'alto'

export const ROTULO_RISCO: Record<NivelRisco, string> = {
  baixo: 'Risco baixo',
  medio: 'Risco médio',
  alto: 'Risco alto',
}

export const ROTULO_DIMENSAO = ROTULO_DIMENSAO_PONTO as Record<DimensaoPonto, string>

export const ORDEM_DIMENSOES: DimensaoPonto[] = ['horas_extras', 'intervalos', 'descanso', 'registro']

/** Unidade (singular/plural) de cada tipo; a ordem das chaves é a ordem dos blocos na tela. O rótulo está em utils/rotulos.ts. */
export const TIPOS_DIVERGENCIA: Record<string, { unidade: [string, string] }> = {
  horas_extras_acima_limite: { unidade: ['dia', 'dias'] },
  semana_acima_limite: { unidade: ['semana', 'semanas'] },
  intervalo_intrajornada_insuficiente: { unidade: ['dia', 'dias'] },
  interjornada_insuficiente: { unidade: ['dia', 'dias'] },
  descanso_semanal_ausente: { unidade: ['semana', 'semanas'] },
  marcacao_invalida: { unidade: ['ocorrência', 'ocorrências'] },
  total_declarado_divergente: { unidade: ['ocorrência', 'ocorrências'] },
  espelho_incompleto: { unidade: ['ocorrência', 'ocorrências'] },
}

export const nivelDeRisco = (percentual: number): NivelRisco =>
  percentual >= FAIXAS_RISCO.alto ? 'alto' : percentual >= FAIXAS_RISCO.medio ? 'medio' : 'baixo'

export const rotuloTipo = (tipo: string): string => rotulo(ROTULO_DIVERGENCIA, tipo)

/** Lista dos campos ausentes do espelho, com o nome em português ("Nome do empregador, CPF do trabalhador"). */
export const listarCamposEspelho = (campos: string[]): string =>
  campos.map((c) => rotulo(ROTULO_CAMPO_ESPELHO, c)).join(', ')

export const contagemTipo = (tipo: string, n: number): string => {
  const [singular, plural] = TIPOS_DIVERGENCIA[tipo]?.unidade ?? ['ocorrência', 'ocorrências']
  return `${n} ${n === 1 ? singular : plural}`
}

/** Minutos em "2h 30min" (ou "45min"). */
export const formatarMinutos = (minutos: number): string => {
  const total = Math.round(minutos)
  const h = Math.floor(total / 60)
  const m = total % 60
  if (h === 0) return `${m}min`
  return m === 0 ? `${h}h` : `${h}h ${String(m).padStart(2, '0')}min`
}

/** AAAA-MM-DD -> dd/mm/aaaa, sem passar por Date (new Date('AAAA-MM-DD') é UTC e desloca o dia no Brasil). */
export const formatarData = (iso: string | null | undefined, comAno = true): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso ?? '')
  if (!m) return iso ?? '—'
  return comAno ? `${m[3]}/${m[2]}/${m[1]}` : `${m[3]}/${m[2]}`
}

/** Dia anterior de uma data AAAA-MM-DD, calculado em UTC só para o calendário (sem fuso). */
export const diaAnterior = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]) - 1))
  return d.toISOString().slice(0, 10)
}

/** "08:00" -> "08:00"; "02:00+1" -> "02:00 (+1)"; datetime ISO -> "HH:MM". */
export const formatarMarca = (marca: string): string => {
  if (marca.endsWith('+1')) return `${marca.slice(0, -2)} (+1)`
  const iso = /T(\d{2}:\d{2})/.exec(marca)
  return iso ? iso[1] : marca
}

export interface Grupo {
  tipo: string
  itens: Divergencia[]
  minutos: number
  basesLegais: string[]
}

/** Agrupa por tipo, na ordem de TIPOS_DIVERGENCIA (tipos desconhecidos vão depois) e por data dentro de cada grupo. */
export const agruparDivergencias = (divergencias: Divergencia[]): Grupo[] => {
  const porTipo = new Map<string, Divergencia[]>()
  for (const d of divergencias) porTipo.set(d.tipo, [...(porTipo.get(d.tipo) ?? []), d])
  const ordem = Object.keys(TIPOS_DIVERGENCIA)
  const tipos = [...porTipo.keys()].sort((a, b) => {
    const ia = ordem.indexOf(a)
    const ib = ordem.indexOf(b)
    return (ia === -1 ? ordem.length : ia) - (ib === -1 ? ordem.length : ib)
  })
  return tipos.map((tipo) => {
    const itens = [...(porTipo.get(tipo) ?? [])].sort((a, b) => (a.data ?? '').localeCompare(b.data ?? ''))
    return {
      tipo,
      itens,
      minutos: itens.reduce((soma, d) => soma + (d.minutos ?? 0), 0),
      basesLegais: [...new Set(itens.map((d) => d.base_legal).filter(Boolean))],
    }
  })
}

/** Texto sob o risco geral: avisa que o resultado é parcial quando alguma dimensão não foi avaliada. */
export const textoBaseRisco = (scores: AnalisePonto['scores_dimensao']): string => {
  const total = ORDEM_DIMENSOES.length
  const naoAvaliadas = ORDEM_DIMENSOES.filter((d) => scores?.[d]?.nao_avaliada).length
  return naoAvaliadas === 0
    ? `É o maior risco entre as ${total} dimensões abaixo.`
    : `É o maior risco entre as ${total - naoAvaliadas} dimensões avaliadas; ${naoAvaliadas} não avaliada${naoAvaliadas > 1 ? 's' : ''}.`
}

// ---------------------------------------------------------------------------------------------
// Regra de jornada aplicada
// ---------------------------------------------------------------------------------------------
/** Valor do parâmetro na data (a última vigência com `desde` <= data), ou o valor de base. */
const valorNaData = (p: ParametroPerfilGravado | undefined, data: string | null): number | null => {
  if (!p || typeof p.valor !== 'number') return null
  let valor = p.valor
  if (data) {
    for (const v of [...(p.vigencias ?? [])].sort((a, b) => a.desde.localeCompare(b.desde))) {
      if (v.desde <= data) valor = v.valor
    }
  }
  return valor
}

const pct = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })

/** "8h por dia, até 2h extras, adicional de 50%", lido do perfil gravado na análise. Vazio sem perfil gravado. */
export const resumoValoresDoPerfil = (analise: Pick<AnalisePonto, 'perfil' | 'marcacoes'>): string => {
  const perfil = analise.perfil
  if (!perfil) return ''
  const datas = (analise.marcacoes ?? []).map((m) => m.data).sort()
  const data = datas.length > 0 ? datas[datas.length - 1] : null
  const jornada = valorNaData(perfil.jornada_diaria_min, data)
  const extras = valorNaData(perfil.extras_max_dia_min, data)
  const adicional = valorNaData(perfil.adicional_extra_pct, data)
  const partes: string[] = []
  if (jornada != null) partes.push(`${formatarMinutos(jornada)} por dia`)
  if (extras != null) partes.push(`até ${formatarMinutos(extras)} extras`)
  if (adicional != null) partes.push(`adicional de ${pct.format(adicional)}%`)
  return partes.join(', ')
}

/** Frase do topo da auditoria. Sem o nome (quem não vê a convenção), mostra só os valores. */
export const textoRegraAplicada = (analise: AnalisePonto): string | null => {
  const valores = resumoValoresDoPerfil(analise)
  const nome = analise.perfil_nome_legivel?.trim() || ''
  if (nome && valores) return `Regra aplicada: ${nome} (${valores})`
  if (nome) return `Regra aplicada: ${nome}`
  if (valores) return `Regra aplicada: ${valores}`
  return null
}

// ---------------------------------------------------------------------------------------------
// Diferenças entre o cálculo do sistema e a leitura da IA
// ---------------------------------------------------------------------------------------------
const ROTULO_CAMPO_DECLARADO: Record<string, string> = {
  total_horas: 'Total de horas declarado',
  horas_extras: 'Horas extras declaradas',
}

/** Uma frase por valor que divergiu: o que era, o valor do sistema e o lido pela IA. */
export const descreverDiferenca = (d: DiferencaGemini): string => {
  const base = d.campo && ROTULO_CAMPO_DECLARADO[d.campo] ? ROTULO_CAMPO_DECLARADO[d.campo] : rotuloTipo(d.tipo ?? '')
  const nome = d.data ? `${base} em ${formatarData(d.data)}` : base
  const sistema = d.minutos_codigo != null ? formatarMinutos(d.minutos_codigo) : null
  const ia = d.minutos_gemini != null ? formatarMinutos(d.minutos_gemini) : null
  if (d.motivo === 'so_codigo') {
    return `${nome}: o sistema apontou${sistema ? ` ${sistema}` : ''}, mas a leitura da IA não apontou. Vale o cálculo do sistema.`
  }
  if (d.motivo === 'so_gemini') {
    return `${nome}: a leitura da IA apontou${ia ? ` ${ia}` : ''}, mas o sistema não confirmou. Vale o cálculo do sistema.`
  }
  if (sistema && ia) {
    return `${nome}: o sistema calculou ${sistema} e a leitura da IA trouxe ${ia}. Vale o cálculo do sistema.`
  }
  return `${nome}: o cálculo do sistema e a leitura da IA não batem. Vale o cálculo do sistema.`
}
