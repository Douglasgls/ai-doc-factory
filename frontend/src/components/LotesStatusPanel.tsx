import React from 'react'
import { AlertTriangle, CheckCircle2, Loader2, X } from 'lucide-react'
import { trackedStatus, type TrackedLote } from '../hooks/lotePollingLogic'

interface LotesStatusPanelProps {
  lotes: TrackedLote[]
  onRecheck: (id: number) => void
  onDismiss: (id: number) => void
  onRetry?: (id: number) => void
}

const CARD =
  'w-full rounded-2xl border p-3.5 sm:p-4 flex items-start justify-between gap-3 bg-white dark:bg-[#1a1120] border-[#ebe5ef] dark:border-[#2f1e39] shadow-xs'

export const LotesStatusPanel: React.FC<LotesStatusPanelProps> = ({
  lotes,
  onRecheck,
  onDismiss,
  onRetry,
}) => {
  if (lotes.length === 0) return null

  return (
    <section className="space-y-2 mb-6" aria-label="Lotes enviados nesta sessão" data-testid="lotes-status">
      {lotes.map((lote) => {
        const status = trackedStatus(lote)
        const nome = lote.nome || `#${lote.id}`
        return (
          <div key={lote.id} className={CARD} data-testid={`lote-${lote.id}`} data-status={status}>
            <div className="flex items-start gap-3 min-w-0">
              <div
                className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center ${
                  status === 'erro' || status === 'cancelado'
                    ? 'bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400'
                    : status === 'concluido'
                      ? 'bg-green-100 dark:bg-green-950/30 text-green-600 dark:text-green-400'
                      : status === 'timeout'
                        ? 'bg-amber-100 dark:bg-amber-950/30 text-amber-600 dark:text-amber-400'
                        : 'bg-[#f7edf9] dark:bg-[#2a1633] text-[#9333ea] dark:text-[#d67bf3]'
                }`}
              >
                {status === 'erro' || status === 'cancelado' || status === 'timeout' ? (
                  <AlertTriangle className="w-5 h-5" />
                ) : status === 'concluido' ? (
                  <CheckCircle2 className="w-5 h-5" />
                ) : (
                  <Loader2 className="w-5 h-5 animate-spin" />
                )}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-[#2d0a33] dark:text-[#f8f5fc] leading-snug break-words">
                  {status === 'erro' &&
                    `O processamento do lote ${nome} falhou. Envie o arquivo novamente para reprocessar.`}
                  {status === 'cancelado' &&
                    `O processamento do lote ${nome} foi cancelado pelo usuário.`}
                  {status === 'concluido' && `Lote ${nome} processado.`}
                  {status === 'timeout' && `O lote ${nome} ainda está em processamento.`}
                  {status === 'processando' &&
                    `Processando o lote ${nome}${lote.mensagemAtual ? ` — ${lote.mensagemAtual}` : lote.estado ? ` (${lote.estado}${lote.docsPendentes ? `, ${lote.docsPendentes} documento(s) pendente(s)` : ''})` : ''}...`}
                </p>
                {(status === 'erro' || status === 'cancelado') && onRetry && (
                    <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#9f91a6] mt-0.5">
                      <button
                        type="button"
                        onClick={() => onRetry(lote.id)}
                        className="font-semibold text-[#9333ea] dark:text-[#d67bf3] hover:underline cursor-pointer"
                      >
                        Tentar novamente
                      </button>
                    </p>
                  )}
                {status === 'timeout' && (
                  <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#9f91a6] mt-0.5">
                    Lotes grandes podem demorar. Isso não indica falha.{' '}
                    <button
                      type="button"
                      onClick={() => onRecheck(lote.id)}
                      className="font-semibold text-[#9333ea] dark:text-[#d67bf3] hover:underline cursor-pointer"
                    >
                      Verificar novamente
                    </button>
                  </p>
                )}
                {lote.networkError && status !== 'erro' && status !== 'concluido' && (
                  <p className="text-xs sm:text-sm text-red-600 dark:text-red-400 mt-0.5">
                    Não foi possível consultar o servidor ({lote.networkError}). Tentando novamente...
                  </p>
                )}
              </div>
            </div>
            {status !== 'processando' && (
              <button
                type="button"
                onClick={() => onDismiss(lote.id)}
                aria-label={`Dispensar aviso do lote ${nome}`}
                className="shrink-0 text-[#6e6378] dark:text-[#9f91a6] hover:text-[#2d0a33] dark:hover:text-white cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        )
      })}
    </section>
  )
}
