import { useCallback, useEffect, useRef, useState } from 'react'
import { apiService, AUTH_EXPIRED_EVENT, type LoteStatusResponse } from '../services/api'
import {
  hasTimedOut,
  isEstadoFinal,
  isEtapaEmAndamento,
  nextPollDelay,
  POLL_INITIAL_MS,
  shouldRefreshList,
  shouldWarnNetwork,
  trackedStatus,
  type LoteSnapshot,
  type TrackedLote,
} from './lotePollingLogic'

interface PollRun {
  startedAt: number
  attempt: number
  errors: number
  last: LoteSnapshot | null
  abortController: AbortController
}

const SESSION_STORAGE_KEY = 'evidocs_tracked_lotes_v1'

function carregarLotesSessao(): TrackedLote[] {
  try {
    const raw = sessionStorage.getItem(SESSION_STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((item: TrackedLote) =>
      item.id <= 0
        ? {
            ...item,
            estado: 'erro',
            etapaAtual: 'erro',
            sseAtivo: false,
            mensagemAtual: 'Envio interrompido ao recarregar a página.',
          }
        : item
    )
  } catch {
    return []
  }
}

/**
 * Acompanha os lotes enviados nesta sessão do navegador em tempo real via SSE (Server-Sent Events + Redis Pub/Sub),
 * com persistência em sessionStorage (sobrevive ao F5) e fallback automático para polling.
 */
export function useLotePolling(onProgress: () => void | Promise<void>) {
  const [lotes, setLotes] = useState<TrackedLote[]>(() => carregarLotesSessao())
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())
  const runs = useRef(new Map<number, PollRun>())
  const filesMap = useRef(new Map<number, File>())
  const active = useRef(false)
  const resumedOnMount = useRef(false)
  const onProgressRef = useRef(onProgress)

  useEffect(() => {
    onProgressRef.current = onProgress
  }, [onProgress])

  const patch = useCallback((id: number, changes: Partial<TrackedLote>) => {
    setLotes((prev) => prev.map((l) => (l.id === id ? { ...l, ...changes } : l)))
  }, [])

  const stopOne = useCallback((id: number) => {
    const timer = timers.current.get(id)
    if (timer) clearTimeout(timer)
    timers.current.delete(id)
    const run = runs.current.get(id)
    if (run) {
      run.abortController.abort()
      runs.current.delete(id)
    }
  }, [])

  const stopAll = useCallback(() => {
    timers.current.forEach((t) => clearTimeout(t))
    timers.current.clear()
    runs.current.forEach((r) => r.abortController.abort())
    runs.current.clear()
  }, [])

  const applyStatusUpdate = useCallback(
    async (id: number, run: PollRun, status: LoteStatusResponse, sseAtivo: boolean) => {
      const ev = status.ultimo_evento
      const cancelado = ev?.etapa === 'cancelado'
      patch(id, {
        estado: status.estado,
        docsPendentes: status.docs_pendentes,
        networkError: null,
        etapaAtual: ev?.etapa ?? status.estado,
        mensagemAtual: ev?.mensagem ?? null,
        paginaAtual: ev?.pagina_atual ?? null,
        totalPaginas: ev?.total_paginas ?? null,
        totalDocumentos: ev?.total_documentos ?? (status.documentos ? status.documentos.length : null),
        documentos: status.documentos ?? [],
        historicoEventos: status.historico_eventos ?? [],
        cancelado,
        sseAtivo,
      })
      const snapshot: LoteSnapshot = { estado: status.estado, docsPendentes: status.docs_pendentes }
      const refresh =
        shouldRefreshList(run.last, snapshot) ||
        ev?.etapa === 'concluido' ||
        ev?.etapa === 'extracao_concluida' ||
        ev?.etapa === 'analise_ponto_concluida'
      run.last = snapshot
      if (refresh) {
        await onProgressRef.current()
      }
    },
    [patch]
  )

  const startPolling = useCallback(
    (id: number) => {
      stopOne(id)
      const abortController = new AbortController()
      const run: PollRun = {
        startedAt: Date.now(),
        attempt: 0,
        errors: 0,
        last: null,
        abortController,
      }
      runs.current.set(id, run)

      const stale = () => !active.current || runs.current.get(id) !== run || abortController.signal.aborted

      const fallbackTick = async () => {
        timers.current.delete(id)
        if (stale()) return
        run.attempt += 1
        try {
          const status = await apiService.getLoteStatus(id)
          if (stale()) return
          run.errors = 0
          await applyStatusUpdate(id, run, status, false)
          if (isEstadoFinal(status.estado) && !isEtapaEmAndamento(status.ultimo_evento?.etapa)) {
            runs.current.delete(id)
            return
          }
        } catch (err) {
          if (stale()) return
          run.errors += 1
          if (shouldWarnNetwork(run.errors)) {
            patch(id, {
              networkError:
                err instanceof Error && err.message ? err.message : 'Falha de conexão com o servidor.',
            })
          }
        }
        if (stale()) return
        if (hasTimedOut(run.startedAt, Date.now())) {
          runs.current.delete(id)
          patch(id, { timedOut: true, sseAtivo: false })
          return
        }
        timers.current.set(id, setTimeout(() => void fallbackTick(), nextPollDelay(run.attempt)))
      }

      // Inicia stream SSE em tempo real; se desconectar antes de concluir, cai para o fallback de polling
      void (async () => {
        let ultimaEtapaRecebida: string | null = null
        try {
          await apiService.streamLoteEvents(
            id,
            (payload) => {
              if (!stale()) {
                ultimaEtapaRecebida = payload.ultimo_evento?.etapa ?? null
                void applyStatusUpdate(id, run, payload, true)
              }
            },
            abortController.signal
          )
        } catch {
          // fallback para polling se o SSE cair ou não estiver disponível
        }
        if (stale()) return
        const ultimoEstado = run.last?.estado
        if (isEstadoFinal(ultimoEstado) && !isEtapaEmAndamento(ultimaEtapaRecebida)) {
          patch(id, { sseAtivo: false })
          runs.current.delete(id)
          return
        }
        timers.current.set(id, setTimeout(() => void fallbackTick(), POLL_INITIAL_MS))
      })()
    },
    [applyStatusUpdate, patch, stopOne]
  )

  /** Registra um lote recém-enviado (ou reenviado) e começa a acompanhá-lo via SSE. */
  const track = useCallback(
    (id: number, nome: string) => {
      const agora = new Date().toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
      })
      setLotes((prev) => {
        const novo: TrackedLote = {
          id,
          nome,
          estado: 'recebido',
          docsPendentes: null,
          timedOut: false,
          networkError: null,
          etapaAtual: 'recebido',
          mensagemAtual: 'Arquivo recebido · aguardando fila...',
          paginaAtual: null,
          totalPaginas: null,
          totalDocumentos: null,
          documentos: [],
          historicoEventos: [],
          cancelado: false,
          sseAtivo: true,
          horarioEnvio: `Hoje, ${agora}`,
        }
        return prev.some((l) => l.id === id) ? prev.map((l) => (l.id === id ? novo : l)) : [novo, ...prev]
      })
      startPolling(id)
    },
    [startPolling]
  )

  /**
   * Recebe os arquivos selecionados no modal, adiciona todos imediatamente na lista de "Análises em andamento"
   * e faz o upload + conexão SSE em tempo real sem prender o usuário no modal de upload.
   */
  const uploadFiles = useCallback(
    (files: File[]) => {
      const agora = new Date().toLocaleTimeString('pt-BR', {
        hour: '2-digit',
        minute: '2-digit',
      })
      const baseTempId = -Date.now()
      const placeholders: { tempId: number; file: File; item: TrackedLote }[] = files.map(
        (file, idx) => {
          const tempId = baseTempId - idx
          filesMap.current.set(tempId, file)
          return {
            tempId,
            file,
            item: {
              id: tempId,
              nome: file.name,
              estado: 'recebido',
              docsPendentes: null,
              timedOut: false,
              networkError: null,
              etapaAtual: 'recebido',
              mensagemAtual: 'Enviando arquivo para análise...',
              paginaAtual: null,
              totalPaginas: null,
              totalDocumentos: null,
              documentos: [],
              historicoEventos: [],
              cancelado: false,
              sseAtivo: true,
              horarioEnvio: `Hoje, ${agora}`,
            },
          }
        }
      )

      setLotes((prev) => [...placeholders.map((p) => p.item), ...prev])

      void (async () => {
        for (const { tempId, file } of placeholders) {
          if (!active.current) return
          try {
            const response = await apiService.uploadLote(file)
            const realId = response.lote_id
            filesMap.current.delete(tempId)
            filesMap.current.set(realId, file)
            setLotes((prev) => {
              // Se o lote real já existia na lista (ex: reenvio do mesmo arquivo), remove o duplicado antigo
              const semDuplicado = prev.filter((l) => l.id !== realId || l.id === tempId)
              return semDuplicado.map((l) =>
                l.id === tempId
                  ? {
                      ...l,
                      id: realId,
                      estado: response.estado || 'recebido',
                      etapaAtual: response.estado === 'concluido' ? 'concluido' : 'recebido',
                      mensagemAtual:
                        response.estado === 'concluido'
                          ? 'A análise terminou sem pendências. O documento já está disponível na lista.'
                          : 'Arquivo recebido · iniciando leitura...',
                    }
                  : l
              )
            })
            void onProgressRef.current()
            startPolling(realId)
          } catch (err) {
            patch(tempId, {
              estado: 'erro',
              etapaAtual: 'erro',
              sseAtivo: false,
              mensagemAtual:
                err instanceof Error && err.message
                  ? err.message
                  : 'Falha ao enviar o arquivo.',
            })
          }
        }
      })()
    },
    [patch, startPolling]
  )

  /** Retoma o acompanhamento de um lote que passou do teto de tempo. */
  const recheck = useCallback(
    (id: number) => {
      patch(id, { timedOut: false, networkError: null, cancelado: false })
      startPolling(id)
    },
    [patch, startPolling]
  )

  /** Reenvia ou reprocessa um lote que falhou ou foi cancelado pelo usuário. */
  const retry = useCallback(
    async (id: number) => {
      stopOne(id)
      const fileInMemory = filesMap.current.get(id)

      // Se o lote falhou antes mesmo de receber um ID do servidor (id <= 0) e temos o File em memória
      if (id <= 0 && fileInMemory) {
        patch(id, {
          estado: 'recebido',
          etapaAtual: 'recebido',
          cancelado: false,
          timedOut: false,
          networkError: null,
          sseAtivo: true,
          mensagemAtual: 'Reenviando arquivo para análise...',
        })
        try {
          const response = await apiService.uploadLote(fileInMemory)
          const realId = response.lote_id
          filesMap.current.delete(id)
          filesMap.current.set(realId, fileInMemory)
          setLotes((prev) => {
            const semDuplicado = prev.filter((l) => l.id !== realId || l.id === id)
            return semDuplicado.map((l) =>
              l.id === id
                ? {
                    ...l,
                    id: realId,
                    estado: response.estado || 'recebido',
                    etapaAtual: response.estado === 'concluido' ? 'concluido' : 'recebido',
                    cancelado: false,
                    mensagemAtual: 'Arquivo recebido · iniciando leitura...',
                  }
                : l
            )
          })
          void onProgressRef.current()
          startPolling(realId)
        } catch (err) {
          patch(id, {
            estado: 'erro',
            etapaAtual: 'erro',
            sseAtivo: false,
            mensagemAtual:
              err instanceof Error && err.message ? err.message : 'Falha ao reenviar o arquivo.',
          })
        }
        return
      }

      if (id <= 0) return

      // Lote já registrado no servidor (id > 0): aciona POST /lotes/{id}/reprocessar
      patch(id, {
        estado: 'recebido',
        etapaAtual: 'recebido',
        docsPendentes: null,
        cancelado: false,
        timedOut: false,
        networkError: null,
        sseAtivo: true,
        mensagemAtual: 'Reprocessando arquivo na fila...',
      })
      try {
        await apiService.retryLote(id)
        void onProgressRef.current()
        startPolling(id)
      } catch (err) {
        patch(id, {
          estado: 'erro',
          etapaAtual: 'erro',
          sseAtivo: false,
          mensagemAtual:
            err instanceof Error && err.message
              ? err.message
              : 'Não foi possível reprocessar este arquivo.',
        })
      }
    },
    [patch, startPolling, stopOne]
  )

  /** Cancela o processamento de um lote em andamento no backend e encerra o stream SSE. */
  const cancel = useCallback(
    async (id: number) => {
      stopOne(id)
      patch(id, {
        cancelado: true,
        estado: 'erro',
        docsPendentes: 0,
        etapaAtual: 'cancelado',
        mensagemAtual: 'Processamento cancelado pelo usuário.',
        sseAtivo: false,
      })
      if (id <= 0) return
      try {
        await apiService.cancelLote(id)
        await onProgressRef.current()
      } catch {
        // mesmo que o lote já tivesse terminado, mantém como cancelado na sessão
      }
    },
    [patch, stopOne]
  )

  const dismiss = useCallback(
    (id: number) => {
      stopOne(id)
      filesMap.current.delete(id)
      setLotes((prev) => prev.filter((l) => l.id !== id))
    },
    [stopOne]
  )

  const clearFinished = useCallback(() => {
    setLotes((prev) => prev.filter((l) => trackedStatus(l) === 'processando'))
  }, [])

  // Persiste a lista de lotes no sessionStorage para sobreviver ao F5
  useEffect(() => {
    try {
      if (lotes.length === 0) {
        sessionStorage.removeItem(SESSION_STORAGE_KEY)
      } else {
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(lotes))
      }
    } catch {
      // ignora erro de quota do sessionStorage
    }
  }, [lotes])

  useEffect(() => {
    active.current = true
    const handleExpired = () => {
      stopAll()
      filesMap.current.clear()
      sessionStorage.removeItem(SESSION_STORAGE_KEY)
      setLotes([])
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => {
      active.current = false
      window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
      stopAll()
    }
  }, [stopAll])

  // Ao montar (ex: após F5), retoma o stream SSE para lotes que estavam em andamento na sessão
  useEffect(() => {
    if (resumedOnMount.current) return
    resumedOnMount.current = true
    lotes.forEach((lote) => {
      if (lote.id > 0 && trackedStatus(lote) === 'processando') {
        startPolling(lote.id)
      }
    })
  }, [lotes, startPolling])

  return { lotes, track, uploadFiles, recheck, retry, cancel, dismiss, clearFinished }
}
