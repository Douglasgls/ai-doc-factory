/** Estado e validação do formulário da convenção. Funções puras: a conversão para minutos acontece aqui. */
import type { ParametroEntrada, PerfilJornadaDetalhe } from '../services/api'
import {
  DEF_PARAMETROS,
  GRUPOS,
  grupoDoParametro,
  duracaoParaMinutos,
  horarioParaMinutos,
  minutosParaHorario,
  minutosParaPartes,
  minutosSegundosParaMinutos,
  percentualParaNumero,
  valoresIguais,
  type TipoCampo,
  type ValorComVigencias,
} from './convencoes'

export const NOME_MAX = 100
export const SINDICATO_MAX = 200
export const BASE_LEGAL_MAX = 300

/** O que o usuário digitou; cada tipo de campo usa os seus campos. */
export interface Entrada {
  h: string
  m: string
  s: string
  horario: string
  pct: string
}

export const entradaVazia = (): Entrada => ({ h: '', m: '', s: '', horario: '', pct: '' })

function numeroPct(v: number): string {
  return String(Number(v.toFixed(4))).replace('.', ',')
}

/** Valor em minutos (ou %) nos campos de digitação. */
export function valorParaEntrada(tipo: TipoCampo, valor: number): Entrada {
  const e = entradaVazia()
  if (tipo === 'percentual') return { ...e, pct: numeroPct(valor) }
  if (tipo === 'horario') return { ...e, horario: minutosParaHorario(valor) }
  const p = minutosParaPartes(valor)
  if (tipo === 'duracao_seg') return { ...e, m: String(Number(p.h) * 60 + Number(p.m)), s: p.s }
  return { ...e, h: p.h, m: p.m }
}

/** Campos de digitação em minutos (ou %); null se o valor não for válido. */
export function entradaParaValor(tipo: TipoCampo, e: Entrada): number | null {
  switch (tipo) {
    case 'percentual':
      return percentualParaNumero(e.pct)
    case 'horario':
      return horarioParaMinutos(e.horario)
    case 'duracao_seg':
      return minutosSegundosParaMinutos(e.m, e.s)
    default:
      return duracaoParaMinutos(e.h, e.m)
  }
}

const ERRO_VALOR: Record<TipoCampo, string> = {
  duracao: 'Informe a duração em horas e minutos (minutos de 0 a 59).',
  duracao_seg: 'Informe minutos e segundos (segundos de 0 a 59).',
  horario: 'Informe o horário.',
  percentual: 'Informe um percentual, como 50 ou 12,5.',
}

export interface Datada {
  id: number
  desde: string
  valor: Entrada
  base_legal: string
}

/** Um parâmetro que a convenção muda em relação ao Padrão. */
export interface Alteracao {
  valor: Entrada
  base_legal: string
  datadas: Datada[]
}

export type Escopo = 'geral' | 'prestador' | 'plataforma'

export interface EstadoForm {
  nome: string
  sindicato: string
  vigencia_inicio: string
  vigencia_fim: string
  escopo: Escopo
  prestador_id: string
  alteracoes: Record<string, Alteracao>
  /** Parâmetros fora do catálogo: seguem como estão. */
  preservados: ParametroEntrada[]
  proximoId: number
}

export function escopoDe(c: { geral: boolean; prestador_id: number | null }): Escopo {
  return c.geral ? 'geral' : c.prestador_id !== null ? 'prestador' : 'plataforma'
}

export function estadoInicial(existente: PerfilJornadaDetalhe | null, escopoPadrao: Escopo): EstadoForm {
  const estado: EstadoForm = {
    nome: existente?.nome ?? '',
    sindicato: existente?.sindicato ?? '',
    vigencia_inicio: existente?.vigencia_inicio ?? '',
    vigencia_fim: existente?.vigencia_fim ?? '',
    escopo: existente ? escopoDe(existente) : escopoPadrao,
    prestador_id: existente?.prestador_id != null ? String(existente.prestador_id) : '',
    alteracoes: {},
    preservados: [],
    proximoId: 1,
  }
  for (const p of existente?.proprios ?? []) {
    const d = DEF_PARAMETROS[p.parametro]
    if (!d) {
      estado.preservados.push({ parametro: p.parametro, valor: p.valor, base_legal: p.base_legal, vigente_desde: p.vigente_desde })
      continue
    }
    const alt = (estado.alteracoes[p.parametro] ??= { valor: entradaVazia(), base_legal: '', datadas: [] })
    if (p.vigente_desde === null) {
      alt.valor = valorParaEntrada(d.tipo, p.valor)
      alt.base_legal = p.base_legal
    } else {
      alt.datadas.push({ id: estado.proximoId++, desde: p.vigente_desde, valor: valorParaEntrada(d.tipo, p.valor), base_legal: p.base_legal })
    }
  }
  return estado
}

export interface ResultadoValidacao {
  erros: Record<string, string>
  parametros: ParametroEntrada[]
}

/** Valida o formulário. `padrao` traz o valor do Padrão por parâmetro (para recusar "mudança" sem mudança). */
export function validarForm(
  e: EstadoForm,
  padrao: Record<string, ValorComVigencias>,
  plataforma: boolean,
): ResultadoValidacao {
  const erros: Record<string, string> = {}
  const nome = e.nome.trim()
  if (!nome) erros.nome = 'Informe o nome da convenção.'
  else if (nome.length > NOME_MAX) erros.nome = `Use até ${NOME_MAX} caracteres.`
  if (e.sindicato.trim().length > SINDICATO_MAX) erros.sindicato = `Use até ${SINDICATO_MAX} caracteres.`
  if (e.vigencia_inicio && e.vigencia_fim && e.vigencia_fim < e.vigencia_inicio) {
    erros.vigencia_fim = 'O fim da vigência não pode ser antes do início.'
  }
  if (plataforma && e.escopo === 'prestador' && !e.prestador_id) erros.prestador = 'Escolha o prestador.'

  const parametros: ParametroEntrada[] = []
  const baseLegal = (texto: string, chave: string) => {
    const b = texto.trim()
    if (!b) erros[chave] = 'Informe a base legal da mudança, por exemplo: CCT 2026/2027, cláusula 12ª.'
    else if (b.length > BASE_LEGAL_MAX) erros[chave] = `Use até ${BASE_LEGAL_MAX} caracteres.`
    return b
  }
  for (const g of GRUPOS) {
    for (const d of g.parametros) {
      const alt = e.alteracoes[d.chave]
      if (!alt) continue
      const valor = entradaParaValor(d.tipo, alt.valor)
      if (valor === null) erros[`${d.chave}:valor`] = ERRO_VALOR[d.tipo]
      const base = baseLegal(alt.base_legal, `${d.chave}:base`)
      const base0 = padrao[d.chave]
      if (valor !== null && alt.datadas.length === 0 && base0 && valoresIguais({ valor }, { valor: base0.valor })
          && !(base0.vigencias?.length)) {
        erros[`${d.chave}:valor`] = 'É o mesmo valor do Padrão. Use "Desfazer" ou informe outro valor.'
      }
      if (valor !== null && base) parametros.push({ parametro: d.chave, valor, base_legal: base, vigente_desde: null })
      const vistas = new Set<string>()
      for (const dt of alt.datadas) {
        const k = `${d.chave}:${dt.id}`
        const v = entradaParaValor(d.tipo, dt.valor)
        if (!dt.desde) erros[`${k}:desde`] = 'Informe a data de início.'
        else if (vistas.has(dt.desde)) erros[`${k}:desde`] = 'Já há uma mudança nesta data.'
        vistas.add(dt.desde)
        if (v === null) erros[`${k}:valor`] = ERRO_VALOR[d.tipo]
        const b = baseLegal(dt.base_legal, `${k}:base`)
        if (dt.desde && v !== null && b) parametros.push({ parametro: d.chave, valor: v, base_legal: b, vigente_desde: dt.desde })
      }
    }
  }
  parametros.push(...e.preservados)
  return { erros, parametros }
}

/** Mesmo conjunto de parâmetros, na mesma ordem de comparação (para saber se algo mudou). */
export function chaveParametros(ps: ParametroEntrada[]): string {
  return JSON.stringify(
    [...ps]
      .map((p) => ({ k: `${p.parametro}|${p.vigente_desde ?? ''}`, v: p.valor, b: p.base_legal.trim() }))
      .sort((a, b) => a.k.localeCompare(b.k)),
  )
}

/** Campos de escopo do corpo: só a plataforma os envia. Geral e dono são exclusivos. */
export function escopoParaCorpo(e: EstadoForm): { geral: boolean; prestador_id: number | null } {
  if (e.escopo === 'geral') return { geral: true, prestador_id: null }
  if (e.escopo === 'prestador') return { geral: false, prestador_id: Number(e.prestador_id) }
  return { geral: false, prestador_id: null }
}

/** Quantas regras foram alteradas em cada tema (chave = id do grupo). */
export function alteracoesPorGrupo(alteracoes: Record<string, unknown>): Record<string, number> {
  return Object.fromEntries(GRUPOS.map((g) => [g.id, g.parametros.filter((p) => alteracoes[p.chave]).length]))
}

export interface ErroLocalizado {
  chave: string
  /** Id do tema (aba) do campo; null para os dados de cadastro, que ficam acima das abas. */
  aba: string | null
  /** Id do elemento do campo, para rolar e focar. */
  campoId: string
  texto: string
}

const CADASTRO: Record<string, { campoId: string; texto: string }> = {
  nome: { campoId: 'conv-nome', texto: 'Falta o nome' },
  sindicato: { campoId: 'conv-sindicato', texto: 'Corrija o sindicato' },
  vigencia_fim: { campoId: 'conv-fim', texto: 'Corrija o fim da vigência' },
  prestador: { campoId: 'conv-prestador', texto: 'Falta escolher o prestador' },
}

/** Leva as chaves de erro de `validarForm` ao tema e ao campo de cada uma, na ordem da tela. */
export function localizarErros(erros: Record<string, string>): ErroLocalizado[] {
  const ordemTema = (id: string | null) => (id === null ? -1 : GRUPOS.findIndex((g) => g.id === id))
  const itens: ErroLocalizado[] = []
  for (const chave of Object.keys(erros)) {
    const cad = CADASTRO[chave]
    if (cad) {
      itens.push({ chave, aba: null, ...cad })
      continue
    }
    const [param, meio, fim] = chave.split(':')
    const rotulo = DEF_PARAMETROS[param]?.rotulo ?? param
    const aba = grupoDoParametro(param) ?? null
    const datada = fim !== undefined
    const tipo = datada ? fim : meio
    const k = datada ? `${param}:${meio}` : param
    const campo = tipo === 'base' ? `base-${k}` : tipo === 'desde' ? `desde-${k}` : `val-${k}`
    const texto =
      tipo === 'base' ? `Falta a base legal em ${rotulo}` : tipo === 'desde' ? `Falta a data em ${rotulo}` : `Corrija o valor de ${rotulo}`
    itens.push({ chave, aba, campoId: campo, texto })
  }
  return itens.sort((a, b) => ordemTema(a.aba) - ordemTema(b.aba))
}

/** Quantos campos com erro há em cada tema (chave = id do grupo). */
export function errosPorAba(erros: Record<string, string>): Record<string, number> {
  const r: Record<string, number> = Object.fromEntries(GRUPOS.map((g) => [g.id, 0]))
  for (const e of localizarErros(erros)) if (e.aba) r[e.aba] += 1
  return r
}

/** Resumo do rodapé: "Falta a base legal em Jornada diária (aba Jornada)" ou a contagem com os temas. */
export function resumoErros(erros: Record<string, string>): string {
  const lista = localizarErros(erros)
  if (lista.length === 0) return ''
  const titulo = (id: string | null) => (id === null ? 'dados de cadastro' : `aba ${GRUPOS.find((g) => g.id === id)?.titulo ?? id}`)
  const frase = (e: ErroLocalizado) => `${e.texto} (${titulo(e.aba)})`
  if (lista.length === 1) return frase(lista[0])
  const abas = [...new Set(lista.map((e) => e.aba))].map(titulo).join(', ')
  return `${lista.length} campos precisam de correção, em ${abas}: ${lista.map((e) => e.texto).join('; ')}.`
}
