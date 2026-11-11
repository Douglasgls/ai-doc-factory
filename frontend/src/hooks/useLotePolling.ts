import { useCallback, useEffect, useRef, useState } from 'react'
import { apiService, AUTH_EXPIRED_EVENT } from '../services/api'
import {
  hasTimedOut,
  isEstadoFinal,
  nextPollDelay,
  POLL_INITIAL_MS,
  shouldWarnNetwork,
  type TrackedLote,
} from './lotePollingLogic'

interface PollRun {
  startedAt: number
  attempt: number
  errors: number
}

/**
 * Acompanha os lotes enviados nesta sessão do navegador até um estado final (`concluido` ou `erro`).
 * Intervalo crescente, teto generoso de tempo (depois disso o lote fica como "timeout" e o usuário
 * pode verificar de novo) e erros de rede repetidos expostos em `networkError`.
 */
export function useLotePolling(onProgress: () => void | Promise<void>) {
  const [lotes, setLotes] = useState<TrackedLote[]>([])
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())
  const runs = useRef(new Map<number, PollRun>())
  const active = useRef(false)
  const onProgressRef = useRef(onProgress)

  useEffect(() => {
    onProgressRef.current = onProgress
  }, [onProgress])

  const patch = useCallback((id: number, changes: Partial<TrackedLote>) => {
    setLotes((prev) => prev.map((l) => (l.id === id ? { ...l, ...changes } : l)))
  }, [])

  const stopAll = useCallback(() => {
    timers.current.forEach((t) => clearTimeout(t))
    timers.current.clear()
    runs.current.clear()
  }, [])

  const startPolling = useCallback(
    (id: number) => {
      const existing = timers.current.get(id)
      if (existing) clearTimeout(existing)
      const run: PollRun = { startedAt: Date.now(), attempt: 0, errors: 0 }
      runs.current.set(id, run)

      const stale = () => !active.current || runs.current.get(id) !== run

      const tick = async () => {
        timers.current.delete(id)
        if (stale()) return
        run.attempt += 1
        try {
          const status = await apiService.getLoteStatus(id)
          if (stale()) return
          run.errors = 0
          patch(id, {
            estado: status.estado,
            docsPendentes: status.docs_pendentes,
            networkError: null,
          })
          await onProgressRef.current()
          if (isEstadoFinal(status.estado)) {
            runs.current.delete(id)
            return
          }
        } catch (err) {
          if (stale()) return
          run.errors += 1
          if (shouldWarnNetwork(run.errors)) {
            patch(id, {
              networkError: err instanceof Error && err.message ? err.message : 'Falha de conexão com o servidor.',
            })
          }
        }
        if (stale()) return
        if (hasTimedOut(run.startedAt, Date.now())) {
          runs.current.delete(id)
          patch(id, { timedOut: true })
          return
        }
        timers.current.set(id, setTimeout(() => void tick(), nextPollDelay(run.attempt)))
      }

      timers.current.set(id, setTimeout(() => void tick(), POLL_INITIAL_MS))
    },
    [patch]
  )

  /** Registra um lote recém-enviado (ou reenviado) e começa a acompanhá-lo. */
  const track = useCallback(
    (id: number, nome: string) => {
      setLotes((prev) => {
        const novo: TrackedLote = {
          id,
          nome,
          estado: null,
          docsPendentes: null,
          timedOut: false,
          networkError: null,
        }
        return prev.some((l) => l.id === id) ? prev.map((l) => (l.id === id ? novo : l)) : [novo, ...prev]
      })
      startPolling(id)
    },
    [startPolling]
  )

  /** Retoma o acompanhamento de um lote que passou do teto de tempo. */
  const recheck = useCallback(
    (id: number) => {
      patch(id, { timedOut: false, networkError: null })
      startPolling(id)
    },
    [patch, startPolling]
  )

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
    runs.current.delete(id)
    setLotes((prev) => prev.filter((l) => l.id !== id))
  }, [])

  useEffect(() => {
    active.current = true
    const handleExpired = () => {
      stopAll()
      setLotes([])
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => {
      active.current = false
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
      stopAll()
    }
  }, [stopAll])

  return { lotes, track, recheck, dismiss }
}
