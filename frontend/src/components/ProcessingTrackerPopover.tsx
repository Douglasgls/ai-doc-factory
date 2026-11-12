import React, { useState, useRef, useEffect } from 'react'
import {
  AlertTriangle,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronUp,
  FileText,
  Info,
  Loader2,
  RotateCcw,
  Sparkles,
  Upload,
  X,
} from 'lucide-react'
import { trackedStatus, type TrackedLote } from '../hooks/lotePollingLogic'

interface ProcessingTrackerPopoverProps {
  lotes: TrackedLote[]
  isOpen: boolean
  onToggleOpen: () => void
  onMinimize: () => void
  onOpenUpload: () => void
  onCancel: (id: number) => void
  onRetry: (id: number) => void
  onRecheck: (id: number) => void
  onDismiss: (id: number) => void
  onClearFinished: () => void
  onNavigateCategory?: (slug: string) => void
  onNavigateReview?: () => void
}

const ETAPAS_CHECK = [
  { key: 'leitura', label: 'Leitura' },
  { key: 'classificacao', label: 'Classificação' },
  { key: 'extracao', label: 'Extração' },
  { key: 'validacao', label: 'Validação' },
] as const

const NOMES_CATEGORIAS: Record<string, string> = {
  aso: 'ASO',
  folha_pagamento: 'Folha de Pagamento',
  folha_ponto: 'Folha de Ponto',
  holerite: 'Holerite',
  recibo_ferias: 'Recibo de Férias',
  atestado_medico: 'Atestado Médico',
  contrato_trabalho: 'Contrato de Trabalho',
}

/**
 * Retorna quantas etapas (0 a 4) já foram concluídas e qual está ativa no momento (0 a 3, ou -1 se finalizado).
 */
function resolverProgressoEtapas(lote: TrackedLote): { concluidas: number; ativa: number } {
  const status = trackedStatus(lote)
  if (status === 'concluido') {
    return { concluidas: 4, ativa: -1 }
  }
  const etapa = lote.etapaAtual || lote.estado || 'recebido'
  switch (etapa) {
    case 'recebido':
    case 'ocr':
      return { concluidas: 0, ativa: 0 }
    case 'segmentacao':
    case 'classificando':
      return { concluidas: 1, ativa: 1 }
    case 'extracao':
    case 'extracao_concluida':
      return { concluidas: 2, ativa: 2 }
    case 'analise_ponto':
    case 'analise_ponto_concluida':
      return { concluidas: 3, ativa: 3 }
    case 'concluido':
      return { concluidas: 4, ativa: -1 }
    default:
      return { concluidas: 0, ativa: status === 'processando' ? 0 : -1 }
  }
}

function obterBadgeEtapa(lote: TrackedLote): string {
  const status = trackedStatus(lote)
  if (status === 'concluido') return 'Concluído'
  if (status === 'cancelado') return 'Cancelado'
  if (status === 'erro') return 'Falhou'
  if (status === 'timeout') return 'Demorando'

  const etapa = lote.etapaAtual || lote.estado || 'recebido'
  switch (etapa) {
    case 'recebido':
    case 'ocr':
      return 'Leitura'
    case 'segmentacao':
    case 'classificando':
      return 'Classificando'
    case 'extracao':
    case 'extracao_concluida':
      return 'Extraindo'
    case 'analise_ponto':
    case 'analise_ponto_concluida':
      return 'Validando'
    default:
      return 'Em análise'
  }
}

function resolverDestinoLote(lote: TrackedLote): {
  labelCategoria: string | null
  slugCategoria: string | null
  emRevisao: boolean
} {
  const docs = lote.documentos || []
  if (docs.length === 0) {
    return { labelCategoria: null, slugCategoria: null, emRevisao: false }
  }
  const docRevisao = docs.find((d) => d.estado === 'em_revisao')
  if (docRevisao) {
    return {
      labelCategoria: 'Revisão manual',
      slugCategoria: docRevisao.tipo || null,
      emRevisao: true,
    }
  }
  const docPrincipal = docs.find((d) => d.tipo && NOMES_CATEGORIAS[d.tipo]) || docs[0]
  const slug = docPrincipal?.tipo || null
  return {
    labelCategoria: slug ? NOMES_CATEGORIAS[slug] || slug : null,
    slugCategoria: slug && NOMES_CATEGORIAS[slug] ? slug : null,
    emRevisao: false,
  }
}

export const ProcessingTrackerPopover: React.FC<ProcessingTrackerPopoverProps> = ({
  lotes,
  isOpen,
  onToggleOpen,
  onMinimize,
  onOpenUpload,
  onCancel,
  onRetry,
  onRecheck,
  onDismiss,
  onClearFinished,
  onNavigateCategory,
  onNavigateReview,
}) => {
  const [expandedIds, setExpandedIds] = useState<Record<number, boolean>>({})
  const containerRef = useRef<HTMLDivElement>(null)

  const totalCount = lotes.length
  const activeLotes = lotes.filter((l) => trackedStatus(l) === 'processando')
  const completedLotes = lotes.filter((l) => trackedStatus(l) === 'concluido')
  const failedOrCanceledLotes = lotes.filter((l) => {
    const s = trackedStatus(l)
    return s === 'erro' || s === 'cancelado' || s === 'timeout'
  })

  const activeCount = activeLotes.length
  const completedCount = completedLotes.length
  const issueCount = failedOrCanceledLotes.length

  // Fecha o popover ao clicar fora dele
  useEffect(() => {
    if (!isOpen) return
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        onMinimize()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen, onMinimize])

  const toggleDetails = (id: number, defaultExpanded: boolean) => {
    setExpandedIds((prev) => ({
      ...prev,
      [id]: !(prev[id] ?? defaultExpanded),
    }))
  }

  // Sem lotes enviados na sessão: botão Enviar padrão
  if (totalCount === 0) {
    return (
      <button
        type="button"
        onClick={onOpenUpload}
        className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-semibold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] shadow-sm hover:shadow transition-all cursor-pointer"
      >
        <Upload className="w-4 h-4" />
        <span>Enviar</span>
      </button>
    )
  }

  const allDoneSuccess = activeCount === 0 && issueCount === 0

  return (
    <div ref={containerRef} className="relative flex items-center gap-2.5">
      {/* Botão Novo envio (estilo Figma) */}
      <button
        type="button"
        onClick={onOpenUpload}
        className="flex items-center gap-2 px-3.5 py-2 rounded-xl text-sm font-semibold border transition-all cursor-pointer bg-[#f6eaf9] border-[#dfc0e9] text-[#6d1878] hover:bg-[#eedaf4] dark:bg-[#230e2a] dark:border-[#481d55] dark:text-[#df86f9] dark:hover:bg-[#2f1338]"
      >
        <Upload className="w-4 h-4" />
        <span className="hidden sm:inline">Novo envio</span>
      </button>

      {/* Pílula Acompanhadora no Header (estilo Figma) */}
      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={isOpen}
        data-testid="header-tracker-trigger"
        className={`flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-xl text-sm border transition-all cursor-pointer select-none ${
          activeCount > 0
            ? 'bg-[#f8eefc] border-[#dfb8ee] text-[#2d0a33] dark:bg-[#26112e] dark:border-[#522361] dark:text-white'
            : allDoneSuccess
              ? 'bg-[#e8f8f0] border-[#a7e3c7] text-[#0d3b29] dark:bg-[#0e3224] dark:border-[#1b5e43] dark:text-white'
              : 'bg-red-50 border-red-200 text-red-900 dark:bg-[#2b1219] dark:border-[#521e2b] dark:text-white'
        }`}
      >
        {/* Quadradinho com contador ou spinner */}
        <span
          className={`w-6 h-6 rounded-lg text-xs font-bold flex items-center justify-center shrink-0 ${
            activeCount > 0
              ? 'bg-[#e9cef4] text-[#7a1c87] dark:bg-[#3c1a49] dark:text-[#e598ff]'
              : allDoneSuccess
                ? 'bg-[#c5eedb] text-[#065f46] dark:bg-[#19563c] dark:text-[#6ee7b7]'
                : 'bg-red-200 text-red-900 dark:bg-[#4c1d2b] dark:text-red-300'
          }`}
        >
          {activeCount > 0 ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : allDoneSuccess ? (
            completedCount
          ) : (
            <AlertTriangle className="w-3.5 h-3.5" />
          )}
        </span>

        {/* Texto de resumo */}
        <span className="text-xs sm:text-sm whitespace-nowrap">
          {activeCount > 0 ? (
            <>
              <strong className="font-bold">{`${completedCount} de ${totalCount}`}</strong>{' '}
              <span className="text-[#7e6388] dark:text-[#c59fd3]">em análise</span>
            </>
          ) : allDoneSuccess ? (
            <>
              <strong className="font-bold">{`${completedCount} de ${totalCount}`}</strong>{' '}
              <span className="text-[#2c7a5b] dark:text-[#8ec5ad]">concluídos</span>
            </>
          ) : completedCount === 0 ? (
            <>
              <strong className="font-bold">{`${issueCount} de ${totalCount}`}</strong>{' '}
              <span className="text-red-700 dark:text-red-300">
                {issueCount === 1 ? 'com falha' : 'com falhas'}
              </span>
            </>
          ) : (
            <>
              <strong className="font-bold">{`${completedCount} de ${totalCount}`}</strong>{' '}
              <span className="text-red-700 dark:text-red-300">{`· ${issueCount} erro(s)`}</span>
            </>
          )}
        </span>

        {isOpen ? (
          <ChevronUp
            className={`w-4 h-4 ${
              activeCount > 0
                ? 'text-[#7e6388] dark:text-[#c59fd3]'
                : allDoneSuccess
                  ? 'text-[#2c7a5b] dark:text-[#8ec5ad]'
                  : 'text-red-700 dark:text-red-300'
            }`}
          />
        ) : (
          <ChevronDown
            className={`w-4 h-4 ${
              activeCount > 0
                ? 'text-[#7e6388] dark:text-[#c59fd3]'
                : allDoneSuccess
                  ? 'text-[#2c7a5b] dark:text-[#8ec5ad]'
                  : 'text-red-700 dark:text-red-300'
            }`}
          />
        )}
      </button>

      {/* Popover Flutuante */}
      {isOpen && (
        <div
          data-testid="header-tracker-popover"
          className="fixed sm:absolute right-3 sm:right-0 top-[70px] sm:top-[calc(100%+12px)] w-[calc(100vw-1.5rem)] sm:w-[430px] rounded-2xl border border-[#e6dfec] dark:border-[#2a1d32] bg-white dark:bg-[#140d18] shadow-[0_24px_60px_-12px_rgba(0,0,0,0.75)] z-50 overflow-hidden transition-all"
        >
          {/* Cabeçalho do Popover */}
          <div className="px-6 pt-5 pb-4 border-b border-[#eee8f3] dark:border-[#231829]">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span
                  className={`w-2 h-2 rounded-full ${
                    activeCount > 0
                      ? 'bg-[#df86f9] animate-pulse'
                      : allDoneSuccess
                        ? 'bg-[#34d399]'
                        : 'bg-red-500'
                  }`}
                />
                <span
                  className={`text-[11px] font-bold tracking-[0.08em] uppercase ${
                    activeCount > 0
                      ? 'text-[#9333ea] dark:text-[#df86f9]'
                      : allDoneSuccess
                        ? 'text-[#059669] dark:text-[#34d399]'
                        : 'text-red-600 dark:text-red-400'
                  }`}
                >
                  {activeCount > 0
                    ? 'EM ANDAMENTO'
                    : allDoneSuccess
                      ? 'TUDO PRONTO'
                      : 'AÇÃO NECESSÁRIA'}
                </span>
              </div>

              <button
                type="button"
                onClick={onMinimize}
                aria-label="Fechar painel de análises"
                className="p-1 rounded-lg text-[#8e8296] hover:text-[#2d0a33] dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/5 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <h3 className="text-xl font-bold text-[#2d0a33] dark:text-white mt-1.5">
              {activeCount > 0
                ? 'Análises em andamento'
                : allDoneSuccess
                  ? 'Análises concluídas'
                  : completedCount === 0
                    ? 'Falha no processamento'
                    : 'Análises finalizadas com alerta'}
            </h3>
            <p className="text-sm text-[#7e7287] dark:text-[#8e8296] mt-0.5">
              {activeCount > 0
                ? `${activeCount} ${activeCount === 1 ? 'arquivo sendo processado agora' : 'arquivos sendo processados agora'}`
                : allDoneSuccess
                  ? `${completedCount} ${completedCount === 1 ? 'arquivo processado com sucesso' : 'arquivos processados com sucesso'}`
                  : `${completedCount} concluído(s) · ${issueCount} com falha`}
            </p>
          </div>

          {/* Card de Destaque (Em andamento / Tudo pronto / Falha) */}
          <div className="px-6 pt-5">
            {activeCount > 0 ? (
              <div className="p-4 rounded-xl border bg-[#f9f0fc] border-[#e5c5f0] dark:bg-[#1f1126] dark:border-[#3c2049] flex items-center justify-between gap-3">
                <div className="flex items-center gap-3.5 min-w-0">
                  <div className="w-10 h-10 rounded-xl bg-[#f1dcf8] dark:bg-[#2d1838] text-[#9333ea] dark:text-[#df86f9] flex items-center justify-center shrink-0">
                    <Loader2 className="w-5 h-5 animate-spin" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-sm font-bold text-[#2d0a33] dark:text-white">
                      Analisando seus documentos
                    </p>
                    <p className="text-xs text-[#6e6378] dark:text-[#b49cc0] mt-0.5 truncate">
                      {activeLotes[0]?.mensagemAtual || 'Processando etapas em tempo real...'}
                    </p>
                  </div>
                </div>
              </div>
            ) : allDoneSuccess ? (
              <div className="p-4 rounded-xl border bg-[#eafaf2] border-[#b7ebd3] dark:bg-[#0d261d] dark:border-[#184634] flex items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-[#d0f4e3] dark:bg-[#13382a] text-[#059669] dark:text-[#34d399] flex items-center justify-center shrink-0">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-[#064e3b] dark:text-white">
                    Seus documentos estão prontos
                  </p>
                  <p className="text-xs text-[#047857] dark:text-[#68b898] mt-0.5">
                    Nenhuma ação é necessária agora.
                  </p>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-xl border bg-red-50 border-red-200 dark:bg-[#261117] dark:border-[#4c1d2b] flex items-center gap-3.5">
                <div className="w-10 h-10 rounded-xl bg-red-100 dark:bg-[#3b1622] text-red-600 dark:text-red-400 flex items-center justify-center shrink-0">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-bold text-red-900 dark:text-white">
                    {issueCount === 1
                      ? '1 arquivo não pôde ser concluído'
                      : `${issueCount} arquivos não puderam ser concluídos`}
                  </p>
                  <p className="text-xs text-red-700 dark:text-red-300 mt-0.5">
                    Verifique os lotes com falha abaixo para reprocessar.
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Cabeçalho da Lista: ARQUIVOS RECENTES + Limpar lista */}
          <div className="px-6 mt-5 mb-1 flex items-center justify-between">
            <span className="text-[11px] font-bold tracking-[0.08em] uppercase text-[#8e8296]">
              ARQUIVOS RECENTES
            </span>
            {completedCount + issueCount > 0 && (
              <button
                type="button"
                onClick={onClearFinished}
                className="text-xs font-medium text-[#8e8296] hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer"
              >
                Limpar lista
              </button>
            )}
          </div>

          {/* Lista de Arquivos */}
          <div className="px-6 divide-y divide-[#eee8f3] dark:divide-[#231829] max-h-[360px] overflow-y-auto">
            {lotes.map((lote) => {
              const status = trackedStatus(lote)
              const defaultExpanded = status !== 'concluido'
              const isExpanded = expandedIds[lote.id] ?? defaultExpanded
              const { concluidas, ativa } = resolverProgressoEtapas(lote)
              const numDocs =
                lote.totalDocumentos ?? (lote.documentos ? lote.documentos.length : 0)
              const badgeLabel = obterBadgeEtapa(lote)
              const { labelCategoria, slugCategoria, emRevisao } = resolverDestinoLote(lote)
              const podeTentarNovamente =
                (status === 'erro' || status === 'cancelado') &&
                lote.estado !== 'concluido'

              return (
                <div key={lote.id} className="py-3.5">
                  {/* Linha Principal do Arquivo */}
                  <div
                    role="button"
                    tabIndex={0}
                    onClick={() => toggleDetails(lote.id, defaultExpanded)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        toggleDetails(lote.id, defaultExpanded)
                      }
                    }}
                    className="flex items-center justify-between gap-2 cursor-pointer group select-none"
                  >
                    <div className="flex items-center gap-3.5 min-w-0">
                      {/* Ícone Redondo de Status */}
                      <div
                        className={`w-9 h-9 rounded-full border flex items-center justify-center shrink-0 ${
                          status === 'concluido'
                            ? 'bg-[#eafaf2] border-[#b7ebd3] text-[#059669] dark:bg-[#0f2e22] dark:border-[#1c523c] dark:text-[#34d399]'
                            : status === 'processando'
                              ? 'bg-[#f8eefc] border-[#dfb8ee] text-[#9333ea] dark:bg-[#261430] dark:border-[#4a245e] dark:text-[#df86f9]'
                              : 'bg-red-50 border-red-200 text-red-500 dark:bg-[#2b1219] dark:border-[#521e2b] dark:text-red-400'
                        }`}
                      >
                        {status === 'concluido' ? (
                          <Check className="w-4 h-4 stroke-[2.5]" />
                        ) : status === 'processando' ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <X className="w-4 h-4" />
                        )}
                      </div>

                      {/* Nome do PDF e Horário */}
                      <div className="min-w-0">
                        <p className="text-sm font-bold text-[#2d0a33] dark:text-white group-hover:text-[#9333ea] dark:group-hover:text-[#df86f9] transition-colors truncate">
                          {lote.nome || `documento_${lote.id}.pdf`}
                        </p>
                        <p className="text-xs text-[#8e8296] mt-0.5">
                          {lote.horarioEnvio || 'Hoje'}
                        </p>
                      </div>
                    </div>

                    {/* Pílula de Status + Chevron + Botão X clean para remover individualmente */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span
                        className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${
                          status === 'concluido'
                            ? 'bg-[#eafaf2] text-[#059669] border-[#b7ebd3] dark:bg-[#0f2e22] dark:text-[#34d399] dark:border-[#194835]'
                            : status === 'processando'
                              ? 'bg-[#f8eefc] text-[#9333ea] border-[#dfb8ee] dark:bg-[#281532] dark:text-[#df86f9] dark:border-[#48235a]'
                              : 'bg-red-50 text-red-600 border-red-200 dark:bg-[#2b1219] dark:text-red-400 dark:border-[#521e2b]'
                        }`}
                      >
                        {badgeLabel}
                      </span>

                      <span className="p-1 text-[#8e8296]">
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4" />
                        ) : (
                          <ChevronDown className="w-4 h-4" />
                        )}
                      </span>

                      {status !== 'processando' && (
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            onDismiss(lote.id)
                          }}
                          title="Remover da lista"
                          aria-label={`Remover ${lote.nome} da lista`}
                          className="p-1 rounded-md text-[#8e8296] opacity-40 group-hover:opacity-100 hover:opacity-100 hover:text-[#2d0a33] dark:hover:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-all cursor-pointer"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Card Expandido de Detalhes */}
                  {isExpanded && (
                    <div className="mt-3 ml-12 rounded-xl bg-[#f8f5fa] dark:bg-[#1b1220] border border-[#e6dfec] dark:border-[#2c1f35] p-3.5">
                      {/* Topo: Documentos identificados (+ Categoria se concluído) + Protocolo #id */}
                      <div className="flex items-center justify-between gap-2 text-xs text-[#7e7287] dark:text-[#9e92a8] mb-3 flex-wrap">
                        <div className="flex items-center gap-2 min-w-0 flex-wrap">
                          <span className="flex items-center gap-1.5">
                            <FileText className="w-3.5 h-3.5 text-[#8e8296] shrink-0" />
                            {numDocs > 0
                              ? `${numDocs} ${numDocs === 1 ? 'documento identificado' : 'documentos identificados'}`
                              : status === 'concluido'
                                ? '1 documento identificado'
                                : status === 'erro' || status === 'cancelado'
                                  ? 'Processamento interrompido'
                                  : 'Identificando documentos...'}
                          </span>

                          {labelCategoria && (
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                emRevisao
                                  ? 'bg-amber-50 text-amber-700 border-amber-200 dark:bg-[#2b1f11] dark:text-amber-300 dark:border-[#5c401d]'
                                  : 'bg-[#f3e8f8] text-[#6d1878] border-[#dfc0e9] dark:bg-[#271531] dark:text-[#df86f9] dark:border-[#48235a]'
                              }`}
                            >
                              {labelCategoria}
                            </span>
                          )}
                        </div>

                        <span className="text-[#8e8296] shrink-0">
                          {lote.id > 0 ? `Protocolo #${lote.id}` : 'Enviando...'}
                        </span>
                      </div>

                      {/* 4 Etapas com Check: Leitura | Classificação | Extração | Validação */}
                      <div className="flex items-center justify-between gap-1.5 pb-3 border-b border-[#e6dfec] dark:border-[#2a1d33] flex-wrap">
                        {ETAPAS_CHECK.map((step, idx) => {
                          const isStepDone = idx < concluidas
                          const isStepActive = idx === ativa && status === 'processando'

                          return (
                            <div key={step.key} className="flex items-center gap-1.5">
                              <span
                                className={`w-4 h-4 rounded-full flex items-center justify-center shrink-0 ${
                                  isStepDone
                                    ? 'bg-[#d0f4e3] text-[#059669] dark:bg-[#123829] dark:text-[#34d399]'
                                    : isStepActive
                                      ? 'bg-[#f1dcf8] text-[#9333ea] dark:bg-[#341844] dark:text-[#df86f9]'
                                      : 'bg-[#eae4ef] text-[#8e8296] dark:bg-[#261b2d] dark:text-[#5d5166]'
                                }`}
                              >
                                {isStepDone ? (
                                  <Check className="w-2.5 h-2.5 stroke-[3]" />
                                ) : isStepActive ? (
                                  <Loader2 className="w-2.5 h-2.5 animate-spin" />
                                ) : (
                                  <span className="w-1 h-1 rounded-full bg-current" />
                                )}
                              </span>
                              <span
                                className={`text-[11px] font-medium ${
                                  isStepDone
                                    ? 'text-[#5c5066] dark:text-[#a094aa]'
                                    : isStepActive
                                      ? 'text-[#2d0a33] dark:text-white font-semibold'
                                      : 'text-[#9e92a8] dark:text-[#5d5166]'
                                }`}
                              >
                                {step.label}
                              </span>
                            </div>
                          )
                        })}
                      </div>

                      {/* Aviso de erro de rede / falha de comunicação */}
                      {lote.networkError && (
                        <p className="pt-2 text-xs font-medium text-red-600 dark:text-red-400">
                          Não foi possível consultar o servidor ({lote.networkError}).
                        </p>
                      )}

                      {/* Rodapé do Card Expandido */}
                      <div className="pt-2.5 flex items-center justify-between gap-3">
                        <p className="text-xs text-[#7e7287] dark:text-[#8e8296] leading-relaxed">
                          {status === 'concluido'
                            ? emRevisao
                              ? 'Documento encaminhado para conferência na revisão manual.'
                              : 'A análise terminou sem pendências. O documento já está disponível na lista.'
                            : status === 'processando'
                              ? lote.mensagemAtual || 'Processando documento nas filas de IA...'
                              : status === 'cancelado'
                                ? 'A análise deste arquivo foi cancelada pelo usuário.'
                                : lote.mensagemAtual || 'Não foi possível concluir a análise.'}
                        </p>

                        {/* Link direto para a pasta ou revisão quando concluído */}
                        {status === 'concluido' && emRevisao && onNavigateReview && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onNavigateReview()
                              onMinimize()
                            }}
                            className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-amber-600 dark:text-amber-400 hover:underline cursor-pointer"
                          >
                            <span>Revisar</span>
                            <ArrowUpRight className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {status === 'concluido' && !emRevisao && slugCategoria && onNavigateCategory && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onNavigateCategory(slugCategoria)
                              onMinimize()
                            }}
                            className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-[#9333ea] dark:text-[#df86f9] hover:underline cursor-pointer"
                          >
                            <span>Ver na pasta</span>
                            <ArrowUpRight className="w-3.5 h-3.5" />
                          </button>
                        )}

                        {/* Ação durante processamento: Cancelar */}
                        {status === 'processando' && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onCancel(lote.id)
                            }}
                            className="shrink-0 text-xs font-semibold text-red-500 dark:text-red-400 hover:underline cursor-pointer"
                          >
                            Cancelar
                          </button>
                        )}

                        {/* Tentar novamente somente para lotes em erro/cancelado (nunca concluídos) */}
                        {podeTentarNovamente && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onRetry(lote.id)
                            }}
                            className="shrink-0 inline-flex items-center gap-1 text-xs font-semibold text-[#9333ea] dark:text-[#df86f9] hover:underline cursor-pointer"
                          >
                            <RotateCcw className="w-3 h-3" />
                            <span>Tentar novamente</span>
                          </button>
                        )}

                        {status === 'timeout' && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation()
                              onRecheck(lote.id)
                            }}
                            className="shrink-0 text-xs font-semibold text-[#9333ea] dark:text-[#df86f9] hover:underline cursor-pointer"
                          >
                            Verificar
                          </button>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>

          {/* Rodapé Informativo */}
          <div className="px-6 py-3.5 border-t border-[#eee8f3] dark:border-[#231829] flex items-center gap-2 text-xs text-[#8e8296]">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>Novas análises aparecerão aqui automaticamente.</span>
          </div>
        </div>
      )}
    </div>
  )
}
