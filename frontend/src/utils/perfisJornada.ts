import type { ParametroEntrada, ParametroProprio } from '../services/api'

/** Identificador técnico do perfil de referência (o usuário só vê "Padrão"). */
export const PERFIL_PADRAO = 'clt_padrao'
export const NOME_MAX = 100
export const SINDICATO_MAX = 200
export const BASE_LEGAL_MAX = 300
export const PARAMETROS_MAX = 200

/** Só o rótulo legível; os parâmetros válidos e as unidades vêm do clt_padrao (a API). */
const ROTULOS: Record<string, string> = {
  jornada_diaria_min: 'Jornada diária',
  jornada_semanal_min: 'Jornada semanal',
  tolerancia_marcacao_min: 'Tolerância por marcação',
  tolerancia_dia_min: 'Tolerância por dia',
  extras_max_dia_min: 'Máximo de horas extras por dia',
  adicional_extra_pct: 'Adicional de hora extra',
  interjornada_min: 'Intervalo interjornada',
  descanso_semanal_min: 'Descanso semanal',
  intervalo_longo_acima_min: 'Intervalo longo: jornada acima de',
  intervalo_longo_min: 'Intervalo longo: duração mínima',
  intervalo_curto_acima_min: 'Intervalo curto: jornada acima de',
  intervalo_curto_min: 'Intervalo curto: duração mínima',
  noturno_inicio_min: 'Início do período noturno',
  noturno_fim_min: 'Fim do período noturno',
  hora_noturna_min: 'Duração da hora noturna',
  adicional_noturno_pct: 'Adicional noturno',
}

export function rotuloParametro(parametro: string): string {
  if (ROTULOS[parametro]) return ROTULOS[parametro]
  const t = parametro.replace(/_(min|pct)$/, '').replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

const num = (v: number) => String(Number(v.toFixed(4))).replace('.', ',')

/** Minutos em "8h", "1h30", "52min30s" etc. */
export function minutosPorExtenso(min: number): string {
  const segs = Math.round(min * 60)
  const h = Math.floor(segs / 3600)
  const m = Math.floor((segs % 3600) / 60)
  const s = segs % 60
  if (h === 0) return s ? `${m}min${String(s).padStart(2, '0')}s` : `${m}min`
  if (m === 0 && s === 0) return `${h}h`
  return s
    ? `${h}h${String(m).padStart(2, '0')}min${String(s).padStart(2, '0')}s`
    : `${h}h${String(m).padStart(2, '0')}`
}

const horaDoDia = (min: number) =>
  `${String(Math.floor(min / 60) % 24).padStart(2, '0')}:${String(Math.floor(min % 60)).padStart(2, '0')}`

/** Valor com unidade amigável: minutos também em horas quando fizer sentido; início/fim do noturno como horário. */
export function formatarValor(parametro: string, valor: number, unidade: string): string {
  if (unidade === 'pct') return `${num(valor)}%`
  if (unidade === 'min') {
    if (parametro === 'noturno_inicio_min' || parametro === 'noturno_fim_min') {
      return `${horaDoDia(valor)} (${num(valor)} min desde 00:00)`
    }
    const ext = minutosPorExtenso(valor)
    return `${num(valor)} min${ext !== `${num(valor)}min` ? ` (${ext})` : ''}`
  }
  return `${num(valor)} ${unidade}`
}

export function nomeUnidade(unidade: string): string {
  return unidade === 'pct' ? '%' : unidade === 'min' ? 'minutos' : unidade
}

export function formatarData(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

export interface LinhaForm {
  chave: number
  parametro: string
  valor: string
  base_legal: string
  vigente_desde: string
}

export function linhasDe(proprios: ParametroProprio[]): LinhaForm[] {
  return proprios.map((p, i) => ({
    chave: i,
    parametro: p.parametro,
    valor: String(p.valor),
    base_legal: p.base_legal,
    vigente_desde: p.vigente_desde ?? '',
  }))
}

/** Mesmas regras do backend (PerfilEntrada/ParametroProprio). Devolve a mensagem de erro ou os parâmetros prontos. */
export function validarPerfil(
  nome: string,
  linhas: LinhaForm[],
  validos: Set<string>,
): { erro: string } | { parametros: ParametroEntrada[] } {
  if (!nome) return { erro: 'Informe o nome da convenção.' }
  if (nome.length > NOME_MAX) return { erro: `O nome tem no máximo ${NOME_MAX} caracteres.` }
  if (linhas.length > PARAMETROS_MAX) return { erro: `No máximo ${PARAMETROS_MAX} linhas.` }
  const parametros: ParametroEntrada[] = []
  const vistos = new Set<string>()
  for (const [i, l] of linhas.entries()) {
    const n = i + 1
    if (!validos.has(l.parametro)) return { erro: `Linha ${n}: escolha um parâmetro.` }
    const txt = l.valor.trim().replace(',', '.')
    const valor = txt === '' ? NaN : Number(txt)
    if (!Number.isFinite(valor) || valor < 0) {
      return { erro: `Linha ${n}: o valor deve ser um número maior ou igual a zero.` }
    }
    const base = l.base_legal.trim()
    if (!base) return { erro: `Linha ${n}: a base legal é obrigatória.` }
    if (base.length > BASE_LEGAL_MAX) {
      return { erro: `Linha ${n}: a base legal tem no máximo ${BASE_LEGAL_MAX} caracteres.` }
    }
    const chave = `${l.parametro}|${l.vigente_desde}`
    if (vistos.has(chave)) return { erro: `Linha ${n}: parâmetro repetido com a mesma vigência.` }
    vistos.add(chave)
    parametros.push({ parametro: l.parametro, valor, base_legal: base, vigente_desde: l.vigente_desde || null })
  }
  const semBase = [...new Set(parametros.map((p) => p.parametro))].filter(
    (p) => !parametros.some((x) => x.parametro === p && x.vigente_desde === null),
  )
  if (semBase.length) {
    return { erro: `Falta o valor de base (vigência vazia) para: ${semBase.map(rotuloParametro).join(', ')}.` }
  }
  return { parametros }
}
