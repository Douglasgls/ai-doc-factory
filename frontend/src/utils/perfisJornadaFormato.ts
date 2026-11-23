/** Convenções coletivas: grupos por tema, valores em linguagem comum e conversões. Funções puras, sem React. */
import { formatarData } from './perfisJornada'

/** Como o usuário informa o valor: horas e minutos, minutos e segundos, horário ou percentual. */
export type TipoCampo = 'duracao' | 'duracao_seg' | 'horario' | 'percentual'

export interface DefParametro {
  chave: string
  rotulo: string
  tipo: TipoCampo
  /** Valor (em minutos ou %) em linguagem comum. */
  frase: (valor: number) => string
}

export interface GrupoParametros {
  id: string
  titulo: string
  parametros: DefParametro[]
}

const MIN_DIA = 1440
const num = (v: number) => String(Number(v.toFixed(4))).replace('.', ',')

/** Minutos em "7h20", "8h", "5 min", "1h30", "52min30s". */
export function formatarDuracao(min: number): string {
  const segs = Math.round(min * 60)
  const h = Math.floor(segs / 3600)
  const m = Math.floor((segs % 3600) / 60)
  const s = segs % 60
  if (h === 0) return s ? `${m}min${String(s).padStart(2, '0')}s` : `${m} min`
  if (m === 0 && s === 0) return `${h}h`
  const base = `${h}h${String(m).padStart(2, '0')}`
  return s ? `${base}min${String(s).padStart(2, '0')}s` : base
}

/** Minutos desde 00:00 em "22:00" (acima de 24h volta ao dia seguinte). */
export function minutosParaHorario(min: number): string {
  const t = ((Math.round(min) % MIN_DIA) + MIN_DIA) % MIN_DIA
  return `${String(Math.floor(t / 60)).padStart(2, '0')}:${String(t % 60).padStart(2, '0')}`
}

/** "05:00" (valor do input time) em minutos desde 00:00; null se inválido. */
export function horarioParaMinutos(horario: string): number | null {
  const m = /^(\d{1,2}):(\d{2})$/.exec(horario.trim())
  if (!m) return null
  const h = Number(m[1])
  const min = Number(m[2])
  if (h > 23 || min > 59) return null
  return h * 60 + min
}

export function formatarPercentual(pct: number): string {
  return `${num(pct)}%`
}

/** "50", "50,5" ou "50%" em número; null se vazio, negativo ou inválido. */
export function percentualParaNumero(texto: string): number | null {
  const t = texto.trim().replace('%', '').replace(',', '.').trim()
  if (t === '' || !/^\d+(\.\d+)?$/.test(t)) return null
  return Number(t)
}

/** Duração em partes para os campos de horas, minutos e segundos. */
export function minutosParaPartes(min: number): { h: string; m: string; s: string } {
  const segs = Math.round(min * 60)
  return {
    h: String(Math.floor(segs / 3600)),
    m: String(Math.floor((segs % 3600) / 60)),
    s: String(segs % 60),
  }
}

const inteiro = (t: string): number | null => (/^\d+$/.test(t.trim()) ? Number(t.trim()) : null)

/** Horas e minutos (campo vazio = 0) em minutos; null se algum campo for inválido ou o total for zero. */
export function duracaoParaMinutos(h: string, m: string): number | null {
  const hh = h.trim() === '' ? 0 : inteiro(h)
  const mm = m.trim() === '' ? 0 : inteiro(m)
  if (hh === null || mm === null || mm > 59) return null
  const total = hh * 60 + mm
  return total > 0 ? total : null
}

/** Minutos e segundos (hora noturna) em minutos; null se inválido ou zero. */
export function minutosSegundosParaMinutos(m: string, s: string): number | null {
  const mm = m.trim() === '' ? 0 : inteiro(m)
  const ss = s.trim() === '' ? 0 : inteiro(s)
  if (mm === null || ss === null || ss > 59) return null
  const total = mm + ss / 60
  return total > 0 ? total : null
}

const def = (chave: string, rotulo: string, tipo: TipoCampo, frase: (v: number) => string): DefParametro => ({
  chave,
  rotulo,
  tipo,
  frase,
})

export const GRUPOS: GrupoParametros[] = [
  {
    id: 'jornada',
    titulo: 'Jornada',
    parametros: [
      def('jornada_diaria_min', 'Jornada diária', 'duracao', (v) => `${formatarDuracao(v)} por dia`),
      def('jornada_semanal_min', 'Jornada semanal', 'duracao', (v) => `${formatarDuracao(v)} por semana`),
      def('tolerancia_marcacao_min', 'Tolerância por marcação', 'duracao', (v) => `${formatarDuracao(v)} por marcação`),
      def('tolerancia_dia_min', 'Tolerância por dia', 'duracao', (v) => `até ${formatarDuracao(v)} por dia`),
    ],
  },
  {
    id: 'extras',
    titulo: 'Horas extras',
    parametros: [
      def('extras_max_dia_min', 'Limite de horas extras', 'duracao', (v) => `até ${formatarDuracao(v)} por dia`),
      def('adicional_extra_pct', 'Adicional de hora extra', 'percentual', formatarPercentual),
    ],
  },
  {
    id: 'intervalos',
    titulo: 'Intervalos',
    parametros: [
      def('intervalo_longo_acima_min', 'Jornada que pede o intervalo maior', 'duracao', (v) => `jornadas acima de ${formatarDuracao(v)}`),
      def('intervalo_longo_min', 'Intervalo maior', 'duracao', (v) => `mínimo de ${formatarDuracao(v)}`),
      def('intervalo_curto_acima_min', 'Jornada que pede o intervalo menor', 'duracao', (v) => `jornadas acima de ${formatarDuracao(v)}`),
      def('intervalo_curto_min', 'Intervalo menor', 'duracao', (v) => `mínimo de ${formatarDuracao(v)}`),
      def('interjornada_min', 'Intervalo entre jornadas', 'duracao', (v) => `${formatarDuracao(v)} entre jornadas`),
    ],
  },
  {
    id: 'descanso',
    titulo: 'Descanso',
    parametros: [def('descanso_semanal_min', 'Descanso semanal', 'duracao', (v) => `${formatarDuracao(v)} seguidas`)],
  },
  {
    id: 'noturno',
    titulo: 'Trabalho noturno',
    parametros: [
      def('noturno_inicio_min', 'Início do período noturno', 'horario', minutosParaHorario),
      def('noturno_fim_min', 'Fim do período noturno', 'horario', minutosParaHorario),
      def('hora_noturna_min', 'Hora noturna', 'duracao_seg', (v) => `hora noturna de ${formatarDuracao(v)}`),
      def('adicional_noturno_pct', 'Adicional noturno', 'percentual', formatarPercentual),
    ],
  },
]

export const DEF_PARAMETROS: Record<string, DefParametro> = Object.fromEntries(
  GRUPOS.flatMap((g) => g.parametros.map((p) => [p.chave, p] as const)),
)

/** Valor em linguagem comum ("8h por dia"); parâmetro fora do catálogo cai no número puro. */
export function fraseValor(parametro: string, valor: number): string {
  const d = DEF_PARAMETROS[parametro]
  return d ? d.frase(valor) : num(valor)
}

export interface ValorComVigencias {
  valor: number
  base_legal?: string
  vigencias?: { desde: string; valor: number; base_legal?: string }[]
}

/** Mesmo valor de base e mesma linha do tempo de vigências: é o que "igual ao Padrão" significa. */
export function valoresIguais(a: ValorComVigencias | undefined, b: ValorComVigencias | undefined): boolean {
  if (!a || !b) return a === b
  if (Math.abs(a.valor - b.valor) > 1e-9) return false
  const va = a.vigencias ?? []
  const vb = b.vigencias ?? []
  if (va.length !== vb.length) return false
  return va.every((v, i) => v.desde === vb[i].desde && Math.abs(v.valor - vb[i].valor) <= 1e-9)
}

/** Quantos parâmetros do efetivo diferem do Padrão. */
export function contarDiferencas(
  efetivo: Record<string, ValorComVigencias>,
  padrao: Record<string, ValorComVigencias>,
): number {
  return Object.keys(efetivo).filter((k) => !valoresIguais(efetivo[k], padrao[k])).length
}

/** Quantas regras diferem do Padrão em cada tema (chave = id do grupo). Temas sem diferença ficam em 0. */
export function diferencasPorGrupo(
  efetivo: Record<string, ValorComVigencias>,
  padrao: Record<string, ValorComVigencias>,
): Record<string, number> {
  return Object.fromEntries(
    GRUPOS.map((g) => [
      g.id,
      g.parametros.filter((p) => efetivo[p.chave] && !valoresIguais(efetivo[p.chave], padrao[p.chave])).length,
    ]),
  )
}

/** Id do tema a que um parâmetro pertence; undefined se estiver fora do catálogo. */
export const grupoDoParametro = (chave: string): string | undefined => GRUPOS.find((g) => g.parametros.some((p) => p.chave === chave))?.id

/** "A partir de 01/05/2027: 7h por dia" */
export function frasePorData(parametro: string, desde: string, valor: number): string {
  return `A partir de ${formatarData(desde)}: ${fraseValor(parametro, valor)}`
}

export type EstadoVigencia = 'sem_prazo' | 'vigente' | 'vence_em_breve' | 'vencida' | 'futura'

const DIAS_AVISO = 30

const diasAte = (de: string, ate: string): number =>
  Math.round((Date.parse(`${ate}T00:00:00Z`) - Date.parse(`${de}T00:00:00Z`)) / 86_400_000)

/** Estado e texto da vigência em `hoje` (AAAA-MM-DD). Vence em breve: até 30 dias. */
export function descreverVigencia(
  inicio: string | null,
  fim: string | null,
  hoje: string,
): { estado: EstadoVigencia; texto: string } {
  if (inicio && inicio > hoje) return { estado: 'futura', texto: `Começa em ${formatarData(inicio)}` }
  if (fim && fim < hoje) return { estado: 'vencida', texto: `Vencida em ${formatarData(fim)}` }
  if (fim) {
    return diasAte(hoje, fim) <= DIAS_AVISO
      ? { estado: 'vence_em_breve', texto: `Vence em ${formatarData(fim)}` }
      : { estado: 'vigente', texto: `Vigente até ${formatarData(fim)}` }
  }
  if (inicio) return { estado: 'vigente', texto: `Vigente desde ${formatarData(inicio)}` }
  return { estado: 'sem_prazo', texto: 'Sem prazo definido' }
}

export function hojeIso(d = new Date()): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/** Resumo do Padrão e escopo: "Geral", "De <prestador>" ou "Só plataforma". */
export function rotuloEscopo(
  c: { geral: boolean; prestador_id: number | null },
  nomePrestador: (id: number) => string | undefined,
): string {
  if (c.geral) return 'Geral'
  if (c.prestador_id !== null) return `De ${nomePrestador(c.prestador_id) ?? 'um prestador'}`
  return 'Só plataforma'
}
