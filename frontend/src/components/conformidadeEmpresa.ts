// Tipos e funções puras da explicação do score de conformidade de uma empresa.
// Formato real: GET /empresas/{cnpj}/conformidade (app/routers/empresas/actions.py), calculado em
// app/conformidade.py::calcular_empresa. Tudo aqui é derivado dos dados da API; nada é inventado.
import { formatarData } from './auditoriaPonto'

export type Classificacao = 'Regular' | 'Atenção' | 'Crítico'
export type CriterioChave = 'completude' | 'validade' | 'consistencia'

export interface Criterio {
  /** Peso nominal em pontos percentuais (40, 35, 25). */
  peso: number
  /** Peso depois de redistribuir os critérios sem nada para avaliar (em pontos percentuais, soma 100). */
  peso_efetivo: number | null
  /** 0 a 1; null quando pendente ou não aplicável. */
  nota: number | null
  pendente: boolean
  aplicavel: boolean
  bons?: number
  ruins?: number
}

export interface ValorComparado {
  documento: number
  tipo: string
  valor: string
}

export interface Desconto {
  criterio: CriterioChave
  documento: number | null
  tipo: string | null
  /** obrigatorio_ausente | documento_vencido | campo_divergente (outros valores caem no fallback). */
  regra: string
  detalhe: string
  pontos: number
  campo?: string
  conferir?: boolean
  /** Já vem mascarado pela API. */
  cpf?: string
  valores?: ValorComparado[]
}

export interface Pendencia {
  criterio: CriterioChave | 'geral'
  documento: number | null
  tipo: string | null
  motivo: string
}

export interface Avaliacao {
  score: number | null
  score_bruto: number | null
  classificacao: Classificacao | null
  provisorio: boolean
  criterios: Record<CriterioChave, Criterio>
  descontos: Desconto[]
  pendencias: Pendencia[]
}

export interface ConformidadeEmpresa {
  cnpj: string
  razao_social: string | null
  documentos_por_tipo: Record<string, number>
  /** AAAA-MM-DD */
  data_referencia: string
  geral: Avaliacao
  por_tipo: Record<string, Avaliacao>
  /** Chave = id do documento. */
  por_documento: Record<string, Avaliacao>
}

/** Tipo documental -> nome em português (vem de GET /tipos). */
export type Rotulos = Record<string, string>

/** Dados de um documento (de GET /documentos), só para dar nome aos ids. */
export interface InfoDocumento {
  tipo: string | null
  nome_arquivo?: string
  lote_id?: number
}

// Faixas de classificação, só para exibir a legenda. A fonte da verdade é FAIXAS em app/conformidade.py:
// (Regular 85, Atenção 65, Crítico 0). A classificação em si vem pronta da API.
export const FAIXAS_CONFORMIDADE: { nome: Classificacao; minimo: number; maximo: number }[] = [
  { nome: 'Regular', minimo: 85, maximo: 100 },
  { nome: 'Atenção', minimo: 65, maximo: 84 },
  { nome: 'Crítico', minimo: 0, maximo: 64 },
]

export const ORDEM_CRITERIOS: CriterioChave[] = ['completude', 'validade', 'consistencia']

export const CRITERIOS: Record<CriterioChave, { rotulo: string; mede: string }> = {
  completude: { rotulo: 'Completude', mede: 'Mede se a empresa enviou todos os documentos obrigatórios.' },
  validade: {
    rotulo: 'Validade',
    mede: 'Mede se os documentos com prazo (ASO e contrato por prazo determinado) estão dentro da validade.',
  },
  consistencia: {
    rotulo: 'Consistência',
    mede: 'Mede se as informações batem entre os documentos: razão social e, para o mesmo CPF, nome, matrícula e data de admissão.',
  },
}

const ROTULO_CAMPO: Record<string, string> = {
  razao_social_prestadora: 'razão social da prestadora',
  nome: 'nome',
  matricula: 'matrícula',
  data_admissao: 'data de admissão',
}

export const rotuloCampo = (campo: string | undefined): string =>
  campo ? (ROTULO_CAMPO[campo] ?? campo.replace(/_/g, ' ')) : 'campo'

/** Tipo que a API usa quando a confiança ficou abaixo do mínimo (app/config.py); não está em /tipos. */
const TIPO_DESCONHECIDO = 'desconhecido'

export const rotuloTipoDoc = (tipo: string | null | undefined, rotulos: Rotulos): string =>
  !tipo ? 'Documento' : tipo === TIPO_DESCONHECIDO ? 'Documento de tipo não identificado' : (rotulos[tipo] ?? tipo.replace(/_/g, ' '))

/** Forma curta para usar no meio de uma frase: sem parênteses e em minúsculas ("ASO", "folha de ponto"). */
export const rotuloEmFrase = (tipo: string | null | undefined, rotulos: Rotulos): string => {
  const base = rotuloTipoDoc(tipo, rotulos).replace(/\s*\([^)]*\)/g, '').trim()
  return /^[A-ZÀ-Ý]{2,}/.test(base) ? base : base.charAt(0).toLowerCase() + base.slice(1)
}

/** ["a", "b", "c"] -> "a, b e c". */
export const listaPt = (itens: string[]): string =>
  itens.length <= 1 ? (itens[0] ?? '') : `${itens.slice(0, -1).join(', ')} e ${itens[itens.length - 1]}`

const plural = (n: number, singular: string, plur: string): string => `${n} ${n === 1 ? singular : plur}`

const pt1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 })
export const formatarPontos = (pontos: number): string => pt1.format(pontos)
export const formatarPercentual = (fracao: number): string => `${pt1.format(fracao * 100)}%`

export type CorFaixa = 'verde' | 'ambar' | 'vermelho'
/** Maior é melhor (o inverso do risco de ponto). Usa a classificação da API; sem ela, só pelo número. */
export const corDaFaixa = (classificacao: Classificacao | null | undefined): CorFaixa =>
  classificacao === 'Regular' ? 'verde' : classificacao === 'Atenção' ? 'ambar' : 'vermelho'

// ---------------------------------------------------------------------------------------------
// Pendências
// ---------------------------------------------------------------------------------------------
export type RegraPendencia = 'pendente_revisao' | 'pendente_obrigatorio' | 'campo_ausente' | 'criterio_sem_dados'

/** A API não manda "regra" nas pendências; ela é deduzida do critério e do motivo (app/conformidade.py::_avaliar). */
export const regraDaPendencia = (p: Pendencia): RegraPendencia => {
  if (p.criterio === 'geral') return 'pendente_revisao'
  if (p.criterio === 'completude') return 'pendente_obrigatorio'
  if (p.motivo.startsWith('nada analisável')) return 'criterio_sem_dados'
  return 'campo_ausente'
}

/** Motivos pelos quais a nota ainda pode mudar, em linguagem simples. Vazio quando não é provisório. */
export const motivosProvisorio = (g: Avaliacao, rotulos: Rotulos): string[] => {
  const motivos: string[] = []
  const naoAnalisados = g.pendencias.filter((p) => regraDaPendencia(p) === 'pendente_revisao')
  if (naoAnalisados.length > 0) {
    motivos.push(
      `${plural(naoAnalisados.length, 'documento ainda não foi analisado', 'documentos ainda não foram analisados')} ` +
        '(em revisão ou sem tipo definido). Quando a revisão terminar, a nota é recalculada.',
    )
  }
  const obrigatorios = g.pendencias.filter((p) => regraDaPendencia(p) === 'pendente_obrigatorio')
  if (obrigatorios.length > 0) {
    const nomes = listaPt(obrigatorios.map((p) => rotuloEmFrase(p.tipo, rotulos)))
    motivos.push(
      `Não encontramos ${nomes} entre os documentos analisados, mas há documento ainda não identificado que pode ser ` +
        'dele. Por isso a falta não foi descontada por enquanto.',
    )
  }
  for (const chave of ORDEM_CRITERIOS) {
    const c = g.criterios[chave]
    if (c.pendente && c.aplicavel) {
      motivos.push(`${CRITERIOS[chave].rotulo} ainda não tem nada para analisar, e o peso dele passou para os outros critérios.`)
    }
  }
  return motivos
}

// ---------------------------------------------------------------------------------------------
// Resumo em uma frase
// ---------------------------------------------------------------------------------------------
export const gerarResumo = (c: ConformidadeEmpresa, rotulos: Rotulos): string => {
  const g = c.geral
  if (g.score == null || g.classificacao == null) {
    const motivos = motivosProvisorio(g, rotulos)
    return (
      'Ainda não há nota para esta empresa: nenhum critério tem documentos analisados para avaliar.' +
      (motivos.length > 0 ? ' Há documentos aguardando análise ou revisão.' : '')
    )
  }

  const ausentes = g.descontos.filter((d) => d.regra === 'obrigatorio_ausente')
  const vencidos = g.descontos.filter((d) => d.regra === 'documento_vencido')
  const divergentes = g.descontos.filter((d) => d.regra === 'campo_divergente')
  const outros = g.descontos.filter((d) => !['obrigatorio_ausente', 'documento_vencido', 'campo_divergente'].includes(d.regra))

  const partes: string[] = []
  if (ausentes.length > 0) {
    const comp = g.criterios.completude
    const total = (comp.bons ?? 0) + (comp.ruins ?? 0) + g.pendencias.filter((p) => p.criterio === 'completude').length
    const nomes = listaPt(ausentes.map((d) => rotuloEmFrase(d.tipo, rotulos)))
    partes.push(
      `${ausentes.length === 1 ? 'falta' : 'faltam'} ${ausentes.length} dos ${total} documentos obrigatórios: ${nomes}`,
    )
  }
  if (vencidos.length > 0) {
    const nomes = listaPt([...new Set(vencidos.map((d) => rotuloEmFrase(d.tipo, rotulos)))])
    partes.push(`${plural(vencidos.length, 'documento está vencido', 'documentos estão vencidos')} (${nomes})`)
  }
  if (divergentes.length > 0) {
    const campos = listaPt([...new Set(divergentes.map((d) => rotuloCampo(d.campo)))])
    partes.push(
      `${plural(divergentes.length, 'informação diverge', 'informações divergem')} entre documentos (${campos}) e precisa ser conferida`,
    )
  }
  if (outros.length > 0) partes.push(plural(outros.length, 'outro ponto precisa de atenção', 'outros pontos precisam de atenção'))

  if (partes.length === 0) return `${g.classificacao}: nenhum problema encontrado nos documentos analisados até agora.`
  // Separador ";" porque cada parte pode ter a sua própria lista com "e".
  return `${g.classificacao} porque ${partes.join('; ')}.`
}

// ---------------------------------------------------------------------------------------------
// Critérios
// ---------------------------------------------------------------------------------------------
const CONTAGEM: Record<CriterioChave, (bons: number, total: number) => string> = {
  completude: (b, t) => `${b} de ${t} ${t === 1 ? 'obrigatório enviado' : 'obrigatórios enviados'}`,
  validade: (b, t) => `${b} de ${t} ${t === 1 ? 'documento dentro da validade' : 'documentos dentro da validade'}`,
  consistencia: (b, t) => `${b} de ${t} ${t === 1 ? 'conferência sem divergência' : 'conferências sem divergência'}`,
}

export type SituacaoCriterio = 'calculado' | 'pendente' | 'nao_aplica'

export interface CriterioExplicado {
  chave: CriterioChave
  rotulo: string
  mede: string
  situacao: SituacaoCriterio
  /** "1 de 5 obrigatórios enviados", só quando calculado. */
  contagem: string | null
  /** "20%", só quando calculado. */
  nota: string | null
  peso: string
  /** Preenchido só quando o peso efetivo difere do nominal. */
  pesoEfetivo: string | null
  /** Explicação do que aconteceu com o peso, para critério pendente ou não aplicável. */
  aviso: string | null
}

export const explicarCriterio = (chave: CriterioChave, c: Criterio): CriterioExplicado => {
  const base = { chave, rotulo: CRITERIOS[chave].rotulo, mede: CRITERIOS[chave].mede, peso: `${pt1.format(c.peso)}%` }
  if (c.pendente) {
    return {
      ...base,
      situacao: 'pendente',
      contagem: null,
      nota: null,
      pesoEfetivo: null,
      aviso:
        'Isso não vale zero: o peso deste critério passou para os outros, e a nota volta a contá-lo quando houver o que ' +
        'analisar.',
    }
  }
  if (!c.aplicavel) {
    return {
      ...base,
      situacao: 'nao_aplica',
      contagem: null,
      nota: null,
      pesoEfetivo: null,
      aviso: 'Não se aplica a esta avaliação. O peso foi dividido entre os outros critérios.',
    }
  }
  const bons = c.bons ?? 0
  const total = bons + (c.ruins ?? 0)
  const diferente = c.peso_efetivo != null && Math.abs(c.peso_efetivo - c.peso) > 0.05
  return {
    ...base,
    situacao: 'calculado',
    contagem: CONTAGEM[chave](bons, total),
    nota: c.nota != null ? formatarPercentual(c.nota) : null,
    pesoEfetivo: diferente && c.peso_efetivo != null ? `${pt1.format(c.peso_efetivo)}%` : null,
    aviso: null,
  }
}

// ---------------------------------------------------------------------------------------------
// Descontos e ações
// ---------------------------------------------------------------------------------------------
export interface AcaoRecomendada {
  titulo: string
  texto: string
}

/** Uma ação por regra. Regra sem entrada aqui usa o fallback (mostra o `detalhe` da API). */
export const ACOES: Record<string, AcaoRecomendada> = {
  obrigatorio_ausente: {
    titulo: 'Documento obrigatório não enviado',
    texto: 'Peça o documento à prestadora e envie em um novo lote.',
  },
  documento_vencido: {
    titulo: 'Documento vencido',
    texto: 'Peça o documento renovado à prestadora e envie em um novo lote.',
  },
  campo_divergente: {
    titulo: 'Informação divergente entre documentos',
    texto:
      'Confira os valores na imagem dos documentos. Se a leitura errou, corrija o campo na revisão; se o documento está ' +
      'errado, peça a correção à prestadora.',
  },
  pendente_revisao: {
    titulo: 'Documento aguardando revisão',
    texto: 'Conclua a revisão manual do documento. A nota passa a considerá-lo assim que ele for revisado.',
  },
  pendente_obrigatorio: {
    titulo: 'Obrigatório que pode estar num documento não identificado',
    texto: 'Conclua a revisão dos documentos pendentes: um deles pode ser o obrigatório que falta.',
  },
  campo_ausente: {
    titulo: 'Campo ausente ou ilegível',
    texto: 'Confira o documento. Se a informação existe, corrija ou preencha o campo na revisão.',
  },
}

export interface DescontoExplicado {
  titulo: string
  detalhe: string | null
  /** Valores lado a lado, só nas divergências. */
  valores: { rotulo: string; valor: string }[]
  documento: number | null
  tipoRotulo: string
  pontos: number
  regra: string
  conhecida: boolean
}

export const explicarDesconto = (d: Desconto, rotulos: Rotulos): DescontoExplicado => {
  const tipoRotulo = rotuloTipoDoc(d.tipo, rotulos)
  const base = { documento: d.documento, tipoRotulo, pontos: d.pontos, regra: d.regra, valores: [] as DescontoExplicado['valores'] }
  switch (d.regra) {
    case 'obrigatorio_ausente':
      return { ...base, conhecida: true, titulo: `${tipoRotulo}: não foi enviado`, detalhe: 'Documento obrigatório que a empresa ainda não enviou.' }
    case 'documento_vencido': {
      const m = /venceu em (\d{4}-\d{2}-\d{2})/.exec(d.detalhe)
      return {
        ...base,
        conhecida: true,
        titulo: `${tipoRotulo}: vencido`,
        detalhe: m ? `Venceu em ${formatarData(m[1])}.` : d.detalhe,
      }
    }
    case 'campo_divergente':
      return {
        ...base,
        conhecida: true,
        titulo: `Divergência em ${rotuloCampo(d.campo)}`,
        detalhe: d.cpf
          ? `Documentos do mesmo CPF (${d.cpf}) trazem valores diferentes.`
          : 'Documentos da mesma empresa trazem valores diferentes.',
        valores: (d.valores ?? []).map((v) => ({ rotulo: `${rotuloTipoDoc(v.tipo, rotulos)} (documento ${v.documento})`, valor: v.valor })),
      }
    default:
      return { ...base, conhecida: false, titulo: d.detalhe || d.regra.replace(/_/g, ' '), detalhe: null }
  }
}

export interface AcaoAgrupada {
  chave: string
  titulo: string
  texto: string
  /** Itens afetados, sem repetição. */
  itens: string[]
}

/** Junta as ações repetidas: uma linha por regra, com a lista do que ela atinge. */
export const agruparAcoes = (g: Avaliacao, rotulos: Rotulos): AcaoAgrupada[] => {
  const mapa = new Map<string, AcaoAgrupada>()
  const adicionar = (chave: string, fallbackTitulo: string, fallbackTexto: string, item: string) => {
    const acao = ACOES[chave]
    const atual = mapa.get(chave) ?? {
      chave,
      titulo: acao?.titulo ?? fallbackTitulo,
      texto: acao?.texto ?? fallbackTexto,
      itens: [],
    }
    if (!atual.itens.includes(item)) atual.itens.push(item)
    mapa.set(chave, atual)
  }
  const doc = (tipo: string | null, id: number | null) =>
    `${rotuloTipoDoc(tipo, rotulos)}${id != null ? ` (documento ${id})` : ''}`

  for (const d of g.descontos) {
    const item = d.regra === 'campo_divergente' ? rotuloCampo(d.campo) : doc(d.tipo, d.documento)
    // Regra desconhecida: o título é o `detalhe` da API e o texto é genérico.
    adicionar(d.regra, d.detalhe || d.regra, 'Confira este ponto nos documentos da empresa.', item)
  }
  for (const p of g.pendencias) {
    const regra = regraDaPendencia(p)
    if (regra === 'criterio_sem_dados') continue // nada a fazer: passa a contar quando houver documentos
    adicionar(regra, p.motivo, p.motivo, regra === 'pendente_obrigatorio' ? rotuloTipoDoc(p.tipo, rotulos) : `${doc(p.tipo, p.documento)}: ${p.motivo}`)
  }
  return [...mapa.values()]
}

/** Soma dos pontos descontados; bate com 100 - score_bruto (app/conformidade.py). */
export const somaDescontos = (g: Avaliacao): number => g.descontos.reduce((s, d) => s + d.pontos, 0)
