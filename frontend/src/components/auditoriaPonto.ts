// Tipos e funções puras da tela de auditoria de folha de ponto.
// Formato real: GET /documentos/{id}/analise-ponto (app/routers/documentos/actions.py), com `totais`
// vindo de app/ponto.py::apurar_folha (sem `divergencias`) e `marcacoes` como extraído pelo Gemini.

export type TipoDivergencia =
  | 'horas_extras_acima_limite'
  | 'semana_acima_limite'
  | 'intervalo_intrajornada_insuficiente'
  | 'interjornada_insuficiente'
  | 'descanso_semanal_ausente'
  | 'marcacao_invalida'
  | 'total_declarado_divergente'

export interface Divergencia {
  tipo: string
  /** AAAA-MM-DD; null em total_declarado_divergente. */
  data: string | null
  minutos: number | null
  base_legal: string
  detalhe: string
  campo?: string
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
  tipo: string
  data: string | null
  motivo: string
}

export type DimensaoPonto = 'horas_extras' | 'intervalos' | 'descanso' | 'registro'

export interface ScoreDimensao {
  normalizado: number | null
  indeterminada: boolean
}

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
}

/** Faixas do risco em % (maior = pior): abaixo de `medio` é baixo, de `medio` a `alto - 1` é médio, `alto` ou mais é alto. */
export const FAIXAS_RISCO = { medio: 34, alto: 67 } as const

export type NivelRisco = 'baixo' | 'medio' | 'alto'

export const ROTULO_RISCO: Record<NivelRisco, string> = {
  baixo: 'Risco baixo',
  medio: 'Risco médio',
  alto: 'Risco alto',
}

export const ROTULO_DIMENSAO: Record<DimensaoPonto, string> = {
  horas_extras: 'Horas extras',
  intervalos: 'Intervalos',
  descanso: 'Descanso',
  registro: 'Registro de ponto',
}

export const ORDEM_DIMENSOES: DimensaoPonto[] = ['horas_extras', 'intervalos', 'descanso', 'registro']

/** Rótulo e unidade (singular/plural) de cada tipo; a ordem das chaves é a ordem dos blocos na tela. */
export const TIPOS_DIVERGENCIA: Record<string, { rotulo: string; unidade: [string, string] }> = {
  horas_extras_acima_limite: { rotulo: 'Horas extras acima do limite diário', unidade: ['dia', 'dias'] },
  semana_acima_limite: { rotulo: 'Semana acima de 44 horas', unidade: ['semana', 'semanas'] },
  intervalo_intrajornada_insuficiente: { rotulo: 'Intervalo de almoço insuficiente', unidade: ['dia', 'dias'] },
  interjornada_insuficiente: { rotulo: 'Descanso entre jornadas (11h) insuficiente', unidade: ['dia', 'dias'] },
  descanso_semanal_ausente: { rotulo: 'Descanso semanal de 24h ausente', unidade: ['semana', 'semanas'] },
  marcacao_invalida: { rotulo: 'Marcação inválida', unidade: ['ocorrência', 'ocorrências'] },
  total_declarado_divergente: { rotulo: 'Total declarado diverge do calculado', unidade: ['ocorrência', 'ocorrências'] },
}

export const nivelDeRisco = (percentual: number): NivelRisco =>
  percentual >= FAIXAS_RISCO.alto ? 'alto' : percentual >= FAIXAS_RISCO.medio ? 'medio' : 'baixo'

export const rotuloTipo = (tipo: string): string => TIPOS_DIVERGENCIA[tipo]?.rotulo ?? tipo.replace(/_/g, ' ')

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
