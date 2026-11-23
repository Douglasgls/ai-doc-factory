/** Geometria da régua do dia: um dia de exemplo (a partir das 08:00) a partir dos valores de uma convenção. */
import { formatarDuracao, minutosParaHorario } from './perfisJornadaFormato'

export const INICIO_EXEMPLO = 8 * 60
const MIN_DIA = 1440

export interface ParametrosDia {
  jornada: number
  intervalo: number
  extras: number
  noturnoInicio: number
  noturnoFim: number
}

export interface Faixa {
  de: number
  ate: number
}

export interface BlocosDia {
  trabalho: Faixa[]
  intervalo: Faixa | null
  extras: Faixa | null
  noturno: Faixa[]
}

/** Valores do dia a partir do mapa parâmetro -> valor; null se faltar o essencial. */
export function parametrosDoDia(v: Record<string, number | undefined>): ParametrosDia | null {
  const jornada = v.jornada_diaria_min
  if (jornada === undefined) return null
  const longoAcima = v.intervalo_longo_acima_min ?? Infinity
  const curtoAcima = v.intervalo_curto_acima_min ?? Infinity
  const intervalo =
    jornada > longoAcima ? (v.intervalo_longo_min ?? 0) : jornada > curtoAcima ? (v.intervalo_curto_min ?? 0) : 0
  return {
    jornada,
    intervalo,
    extras: v.extras_max_dia_min ?? 0,
    noturnoInicio: v.noturno_inicio_min ?? 22 * 60,
    noturnoFim: v.noturno_fim_min ?? 5 * 60,
  }
}

/** Faixas (em minutos desde 00:00, limitadas a 24h) do dia de exemplo. */
export function blocosDoDia(p: ParametrosDia): BlocosDia {
  const corta = (de: number, ate: number): Faixa | null => {
    const d = Math.max(0, Math.min(de, MIN_DIA))
    const a = Math.max(0, Math.min(ate, MIN_DIA))
    return a > d ? { de: d, ate: a } : null
  }
  const metade = p.jornada / 2
  const ini = INICIO_EXEMPLO
  const fimManha = ini + metade
  const fimIntervalo = fimManha + p.intervalo
  const fimJornada = fimIntervalo + metade
  const trabalho = [corta(ini, fimManha), corta(fimIntervalo, fimJornada)].filter((f): f is Faixa => f !== null)
  const noturno =
    p.noturnoInicio > p.noturnoFim
      ? [corta(0, p.noturnoFim), corta(p.noturnoInicio, MIN_DIA)]
      : [corta(p.noturnoInicio, p.noturnoFim)]
  return {
    trabalho,
    intervalo: p.intervalo > 0 ? corta(fimManha, fimIntervalo) : null,
    extras: p.extras > 0 ? corta(fimJornada, fimJornada + p.extras) : null,
    noturno: noturno.filter((f): f is Faixa => f !== null),
  }
}

/** Texto para leitores de tela: "Jornada de 8h com 1h de intervalo; período noturno das 22:00 às 05:00". */
export function descricaoDoDia(p: ParametrosDia): string {
  const intervalo = p.intervalo > 0 ? ` com ${formatarDuracao(p.intervalo)} de intervalo` : ''
  const extras = p.extras > 0 ? `; até ${formatarDuracao(p.extras)} de horas extras` : ''
  return `Jornada de ${formatarDuracao(p.jornada)}${intervalo}${extras}; período noturno das ${minutosParaHorario(p.noturnoInicio)} às ${minutosParaHorario(p.noturnoFim)}`
}

/** Quais elementos da régua mudam em relação ao Padrão. */
export function diferencas(a: ParametrosDia, b: ParametrosDia): { jornada: boolean; extras: boolean; noturno: boolean } {
  return {
    jornada: a.jornada !== b.jornada || a.intervalo !== b.intervalo,
    extras: a.extras !== b.extras,
    noturno: a.noturnoInicio !== b.noturnoInicio || a.noturnoFim !== b.noturnoFim,
  }
}
