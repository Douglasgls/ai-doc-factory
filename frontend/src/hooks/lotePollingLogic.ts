/** Lógica pura do acompanhamento de lotes (sem React), isolada para ser testável. */

export const POLL_INITIAL_MS = 1500
export const POLL_MAX_MS = 5000
export const POLL_GROWTH = 1.25
/** Teto de acompanhamento antes de mostrar "ainda em processamento". */
export const POLL_TIMEOUT_MS = 15 * 60 * 1000
/** Quantas falhas de rede seguidas até avisar o usuário. */
export const NETWORK_ERRORS_BEFORE_WARNING = 3

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

export type LoteTrackedStatus = 'processando' | 'concluido' | 'erro' | 'timeout'

export interface TrackedLote {
  id: number
  nome: string
  estado: string | null
  docsPendentes: number | null
  timedOut: boolean
  networkError: string | null
}

export const trackedStatus = (lote: TrackedLote): LoteTrackedStatus => {
  if (lote.estado === 'erro') return 'erro'
  if (lote.estado === 'concluido') return 'concluido'
  if (lote.timedOut) return 'timeout'
  return 'processando'
}
