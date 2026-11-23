// Funções puras da busca por texto nos documentos (GET /busca).
import type { DocumentoResponse, SearchResult } from '../services/api'
import type { DetailedDocument } from '../types'

export const MIN_CARACTERES_BUSCA = 2
export const ESPERA_BUSCA_MS = 300

export interface ParteTrecho {
  texto: string
  destaque: boolean
}

/**
 * Converte o trecho da API (texto com <b>termo</b>) em partes. Só o par <b></b> vira destaque;
 * qualquer outro texto, inclusive com "<" ou "&", segue como texto puro e nunca vira HTML.
 */
export const trechoParaPartes = (trecho: string): ParteTrecho[] => {
  const partes: ParteTrecho[] = []
  const regex = /<b>([\s\S]*?)<\/b>/g
  let fim = 0
  let achado: RegExpExecArray | null
  while ((achado = regex.exec(trecho)) !== null) {
    if (achado.index > fim) partes.push({ texto: trecho.slice(fim, achado.index), destaque: false })
    if (achado[1]) partes.push({ texto: achado[1], destaque: true })
    fim = achado.index + achado[0].length
  }
  if (fim < trecho.length) partes.push({ texto: trecho.slice(fim), destaque: false })
  return partes.filter((p) => p.texto !== '')
}

export interface ItemBusca {
  /** Página do lote (é a que o visualizador recebe). */
  pagina: number
  /** Página dentro do documento, contando de 1. */
  paginaNoDocumento: number
  partes: ParteTrecho[]
}

export interface GrupoBusca {
  chave: string
  documentoId: number | null
  loteId: number
  nomeArquivo: string
  pessoa: string | null
  /** Total de páginas do documento; null se a API não informou o intervalo. */
  totalPaginas: number | null
  tipo: string | null
  itens: ItemBusca[]
}

/** Agrupa os resultados por documento, mantendo a ordem de relevância da API (o primeiro resultado define a posição do grupo). */
export const agruparResultados = (resultados: SearchResult[]): GrupoBusca[] => {
  const grupos = new Map<string, GrupoBusca>()
  for (const r of resultados) {
    const chave = r.documento_id != null ? `doc-${r.documento_id}` : `lote-${r.lote_id}-sem-documento`
    let grupo = grupos.get(chave)
    if (!grupo) {
      grupo = {
        chave,
        documentoId: r.documento_id,
        loteId: r.lote_id,
        nomeArquivo: r.nome_documento || r.nome_arquivo,
        pessoa: r.pessoa || null,
        totalPaginas: r.pagina_ini != null && r.pagina_fim != null ? r.pagina_fim - r.pagina_ini + 1 : null,
        tipo: r.tipo,
        itens: [],
      }
      grupos.set(chave, grupo)
    }
    const paginaNoDocumento = r.pagina_ini != null ? r.pagina - r.pagina_ini + 1 : r.pagina
    grupo.itens.push({ pagina: r.pagina, paginaNoDocumento, partes: trechoParaPartes(r.trecho) })
  }
  return [...grupos.values()]
}

/** Documento no formato que o visualizador espera, a partir do detalhe devolvido por GET /documentos/{id}. */
export const documentoParaVisualizador = (d: DocumentoResponse): DetailedDocument => {
  const campos = d.campos || {}
  return {
    id: String(d.id),
    loteId: d.lote_id,
    filename: d.nome_arquivo || `Documento #${d.id}`,
    originalFilename: d.nome_original,
    category: d.tipo || 'desconhecido',
    estado: d.estado,
    personName: d.pessoa || campos.nome || '',
    pages: d.n_paginas ?? d.pagina_fim - d.pagina_ini + 1,
    startPage: d.pagina_ini,
    processedDate: d.processado_em ? new Date(d.processado_em).toLocaleDateString('pt-BR') : '',
    confidence: d.confianca ?? 0,
    campos,
    metadata: {},
  }
}
