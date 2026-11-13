import type { DetailedDocument } from '../types'

export type GroupMode = 'lista' | 'colaborador' | 'competencia'

export interface GrupoColaborador {
  nome: string
  cpf?: string
  matricula?: string
  docs: DetailedDocument[]
}

export interface GrupoCompetencia {
  chave: string
  titulo: string
  docs: DetailedDocument[]
}

/**
 * Retorna as iniciais de um nome (ex: 'Marcos Vinícius Santos' -> 'MS')
 */
export function obterIniciais(nome: string): string {
  const partes = (nome || '').trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase()
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase()
}

/**
 * Converte 'YYYY-MM' para formato amigável 'Outubro de 2026'
 */
export function formatarCompetenciaExtenso(comp: string): string {
  const match = comp.match(/^(\d{4})-(\d{2})$/)
  if (match) {
    const meses = [
      'Janeiro',
      'Fevereiro',
      'Março',
      'Abril',
      'Maio',
      'Junho',
      'Julho',
      'Agosto',
      'Setembro',
      'Outubro',
      'Novembro',
      'Dezembro',
    ]
    const mesIndex = Number(match[2]) - 1
    const mesNome = meses[mesIndex] || match[2]
    return `${mesNome} de ${match[1]}`
  }
  return comp
}

/**
 * Extrai a competência (AAAA-MM) de um documento a partir dos campos disponíveis
 */
export function extrairCompetenciaDoc(doc: DetailedDocument): string {
  const campos = doc.campos || {}
  if (campos.competencia && /^\d{4}-\d{2}/.test(campos.competencia)) {
    return campos.competencia.slice(0, 7)
  }
  if (campos.inicio_ferias && /^\d{4}-\d{2}/.test(campos.inicio_ferias)) {
    return campos.inicio_ferias.slice(0, 7)
  }
  if (campos.data_exame && /^\d{4}-\d{2}/.test(campos.data_exame)) {
    return campos.data_exame.slice(0, 7)
  }
  if (campos.data_emissao && /^\d{4}-\d{2}/.test(campos.data_emissao)) {
    return campos.data_emissao.slice(0, 7)
  }
  if (campos.data_termino && /^\d{4}-\d{2}/.test(campos.data_termino)) {
    return campos.data_termino.slice(0, 7)
  }
  return 'Outros / Sem data'
}

/**
 * Agrupa documentos por Colaborador
 */
export function agruparPorColaborador(documents: DetailedDocument[]): GrupoColaborador[] {
  const map = new Map<string, GrupoColaborador>()
  for (const doc of documents) {
    const nome = doc.personName || 'Não identificado'
    if (!map.has(nome)) {
      map.set(nome, {
        nome,
        cpf: doc.campos?.cpf || doc.metadata?.cpfNumber,
        matricula: doc.campos?.matricula || doc.metadata?.registrationNumber,
        docs: [],
      })
    }
    const g = map.get(nome)!
    if (!g.cpf && (doc.campos?.cpf || doc.metadata?.cpfNumber)) {
      g.cpf = doc.campos?.cpf || doc.metadata?.cpfNumber
    }
    if (!g.matricula && (doc.campos?.matricula || doc.metadata?.registrationNumber)) {
      g.matricula = doc.campos?.matricula || doc.metadata?.registrationNumber
    }
    g.docs.push(doc)
  }
  return Array.from(map.values()).sort((a, b) => a.nome.localeCompare(b.nome))
}

/**
 * Agrupa documentos por Competência / Mês
 */
export function agruparPorCompetencia(documents: DetailedDocument[]): GrupoCompetencia[] {
  const map = new Map<string, GrupoCompetencia>()
  for (const doc of documents) {
    const chave = extrairCompetenciaDoc(doc)
    if (!map.has(chave)) {
      map.set(chave, {
        chave,
        titulo: formatarCompetenciaExtenso(chave),
        docs: [],
      })
    }
    map.get(chave)!.docs.push(doc)
  }
  return Array.from(map.values()).sort((a, b) => {
    // 'Outros / Sem data' fica no final
    if (a.chave === 'Outros / Sem data') return 1
    if (b.chave === 'Outros / Sem data') return -1
    return b.chave.localeCompare(a.chave)
  })
}
