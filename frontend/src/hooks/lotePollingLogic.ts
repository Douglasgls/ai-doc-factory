import type { DocumentoResponse, LoteEventoProgresso } from '../services/api'

/** Lógica pura do acompanhamento de lotes (sem React), isolada para ser testável. */

export const POLL_INITIAL_MS = 1500
export const POLL_MAX_MS = 5000
export const POLL_GROWTH = 1.25
/** Teto de acompanhamento antes de mostrar "ainda em processamento". */
export const POLL_TIMEOUT_MS = 15 * 60 * 1000
/** Quantas falhas de rede seguidas até avisar o usuário. */
export const NETWORK_ERRORS_BEFORE_WARNING = 3
/** Máximo de conexões SSE simultâneas por aba para não esgotar o limite de 6 conexões HTTP/1.1 do navegador. */
export const MAX_CONCURRENT_SSE = 2

export const isEstadoFinal = (estado: string | null | undefined): boolean =>
  estado === 'concluido' || estado === 'erro'

/** Intervalo até a próxima consulta: cresce de POLL_INITIAL_MS até POLL_MAX_MS. `attempt` conta de 1. */
export const nextPollDelay = (attempt: number): number => {
  const delay = POLL_INITIAL_MS * Math.pow(POLL_GROWTH, Math.max(0, attempt - 1))
  return Math.min(POLL_MAX_MS, Math.round(delay))
}

export const hasTimedOut = (startedAt: number, now: number, timeoutMs: number = POLL_TIMEOUT_MS): boolean =>
  now - startedAt >= timeoutMs

export const shouldWarnNetwork = (consecutiveErrors: number): boolean =>
  consecutiveErrors >= NETWORK_ERRORS_BEFORE_WARNING

export interface LoteSnapshot {
  estado: string | null
  docsPendentes: number | null
  etapaAtual?: string | null
}

/**
 * Recarregar a lista só quando algo mudou desde a consulta anterior do mesmo lote
 * (`previous` null = primeira consulta). Não recarrega repetidamente se o estado já era final.
 */
export const shouldRefreshList = (previous: LoteSnapshot | null, next: LoteSnapshot): boolean =>
  previous === null ||
  previous.estado !== next.estado ||
  previous.docsPendentes !== next.docsPendentes

export type LoteTrackedStatus = 'processando' | 'concluido' | 'erro' | 'timeout' | 'cancelado'

export interface TrackedLote {
  id: number
  nome: string
  estado: string | null
  docsPendentes: number | null
  timedOut: boolean
  networkError: string | null
  etapaAtual?: string | null
  mensagemAtual?: string | null
  paginaAtual?: number | null
  totalPaginas?: number | null
  totalDocumentos?: number | null
  documentos?: DocumentoResponse[]
  historicoEventos?: LoteEventoProgresso[]
  cancelado?: boolean
  sseAtivo?: boolean
  horarioEnvio?: string
}

const ETAPAS_EM_ANDAMENTO = new Set([
  'recebido',
  'ocr',
  'segmentacao',
  'classificando',
  'extracao',
  'analise_ponto',
])

export const isEtapaEmAndamento = (etapa: string | null | undefined): boolean =>
  Boolean(etapa && ETAPAS_EM_ANDAMENTO.has(etapa))

export const trackedStatus = (lote: TrackedLote): LoteTrackedStatus => {
  if (lote.cancelado || lote.etapaAtual === 'cancelado') return 'cancelado'
  if (lote.estado === 'erro' || lote.etapaAtual === 'erro') return 'erro'
  if (lote.timedOut) return 'timeout'
  if (lote.estado === 'concluido') {
    return isEtapaEmAndamento(lote.etapaAtual) ? 'processando' : 'concluido'
  }
  return 'processando'
}
