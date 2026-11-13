import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
  FileText,
  Info,
  Maximize2,
  ShieldCheck,
  X,
} from 'lucide-react'
import { apiService, fetchPageImage } from '../services/api'
import {
  ORDEM_DIMENSOES,
  ROTULO_DIMENSAO,
  ROTULO_RISCO,
  agruparDivergencias,
  contagemTipo,
  diaAnterior,
  formatarData,
  formatarMarca,
  formatarMinutos,
  nivelDeRisco,
  rotuloTipo,
  type AnalisePonto,
  type DiaApurado,
  type Divergencia,
  type Grupo,
  type MarcacaoDia,
  type NivelRisco,
} from './auditoriaPonto'

interface Props {
  documentoId: number
  filename: string
  onClose: () => void
}

interface PaginaDoc {
  numero: number
}

const COR_TEXTO: Record<NivelRisco, string> = {
  baixo: 'text-emerald-700 dark:text-emerald-400',
  medio: 'text-amber-700 dark:text-amber-400',
  alto: 'text-red-700 dark:text-red-400',
}

const MUTED = 'text-[#6e6378] dark:text-[#a093a8]'

const faixaMarcas = (m: MarcacaoDia): string =>
  m.pares.map(([e, s]) => `${formatarMarca(e)}–${formatarMarca(s)}`).join('  ·  ')

/** Anel circular SVG de risco (0–100% ou estado ainda não calculado). */
const AnelRisco: React.FC<{
  risco: number | null
  nivel: NivelRisco | null
  indeterminado: boolean
}> = ({ risco, nivel, indeterminado }) => {
  const raio = 36
  const circunferencia = 2 * Math.PI * raio
  const percentual =
    indeterminado || risco == null ? 30 : Math.max(0, Math.min(100, risco))
  const offset =
    !indeterminado && risco === 0
      ? 0
      : circunferencia - (percentual / 100) * circunferencia

  const corTrajeto = indeterminado || nivel == null
    ? '#d97706'
    : nivel === 'baixo'
      ? '#10b981'
      : nivel === 'medio'
        ? '#f59e0b'
        : '#ef4444'

  const corTrilha = indeterminado || nivel == null
    ? 'stroke-[#f3ead8] dark:stroke-[#3b2f1c]'
    : nivel === 'baixo'
      ? 'stroke-emerald-100 dark:stroke-emerald-950/60'
      : nivel === 'medio'
        ? 'stroke-amber-100 dark:stroke-amber-950/60'
        : 'stroke-red-100 dark:stroke-red-950/60'

  return (
    <div
      className="relative w-20 h-20 sm:w-[88px] sm:h-[88px] shrink-0 flex items-center justify-center"
      role="img"
      aria-label={
        indeterminado || risco == null
          ? 'Risco ainda não calculado'
          : `Risco de ${risco}%`
      }
    >
      <svg className="w-full h-full -rotate-90" viewBox="0 0 92 92" aria-hidden="true">
        <circle
          cx="46"
          cy="46"
          r={raio}
          fill="none"
          strokeWidth="6.5"
          className={corTrilha}
        />
        <circle
          cx="46"
          cy="46"
          r={raio}
          fill="none"
          strokeWidth="6.5"
          strokeLinecap="round"
          stroke={corTrajeto}
          strokeDasharray={circunferencia}
          strokeDashoffset={offset}
          className="transition-all duration-500"
        />
      </svg>
      <span
        className={`absolute font-extrabold ${
          indeterminado || risco == null
            ? 'text-xl text-[#92400e] dark:text-amber-300'
            : `text-lg ${nivel ? COR_TEXTO[nivel] : 'text-[#2d0a33] dark:text-white'}`
        }`}
      >
        {indeterminado || risco == null ? '—' : `${risco}%`}
      </span>
    </div>
  )
}

/** Linha de uma divergência, com os horários cruzados de `marcacoes` e `totais.dias`. */
const LinhaDivergencia: React.FC<{
  div: Divergencia
  marcacoes: Map<string, MarcacaoDia>
  dias: Map<string, DiaApurado>
}> = ({ div, marcacoes, dias }) => {
  const falta = div.minutos != null ? formatarMinutos(div.minutos) : null
  const indisponivel = <span className="italic">marcações indisponíveis</span>
  const data = div.data
  const marc = data ? marcacoes.get(data) : undefined
  const dia = data ? dias.get(data) : undefined
  let corpo: React.ReactNode

  switch (div.tipo) {
    case 'horas_extras_acima_limite':
      corpo = (
        <>
          <strong>{formatarData(data)}</strong>: {marc ? faixaMarcas(marc) : indisponivel}
          {dia && <> · trabalhadas {formatarMinutos(dia.trabalhado_min)}</>}
          {falta && <> · {falta} acima do limite</>}
        </>
      )
      break
    case 'intervalo_intrajornada_insuficiente': {
      const lacunas = marc
        ? marc.pares.slice(0, -1).map((p, i) => [p[1], marc.pares[i + 1][0]] as const)
        : []
      corpo = (
        <>
          <strong>{formatarData(data)}</strong>:{' '}
          {!marc ? (
            indisponivel
          ) : lacunas.length === 0 ? (
            <>sem intervalo registrado (jornada de {faixaMarcas(marc)})</>
          ) : (
            <>
              {lacunas
                .map(([s, r]) => `saída ${formatarMarca(s)}, retorno ${formatarMarca(r)}`)
                .join(' · ')}
              {dia && <> · intervalo feito {formatarMinutos(dia.intervalo_min)}</>}
            </>
          )}
          {falta && <> · faltaram {falta}</>}
        </>
      )
      break
    }
    case 'interjornada_insuficiente': {
      // A data da divergência é o dia SEGUINTE; a saída vem do dia anterior (app/ponto.py).
      const anterior = data ? diaAnterior(data) : null
      const marcAnt = anterior ? marcacoes.get(anterior) : undefined
      const saida = marcAnt?.pares.length ? marcAnt.pares[marcAnt.pares.length - 1][1] : null
      const entrada = marc?.pares.length ? marc.pares[0][0] : null
      corpo = (
        <>
          {saida && entrada && anterior ? (
            <>
              <strong>
                saída {formatarData(anterior, false)} {formatarMarca(saida)}
              </strong>{' '}
              →{' '}
              <strong>
                entrada {formatarData(data, false)} {formatarMarca(entrada)}
              </strong>
            </>
          ) : (
            <>
              <strong>{formatarData(data)}</strong>: {indisponivel}
            </>
          )}
          {falta && <> · faltaram {falta} para as 11h</>}
        </>
      )
      break
    }
    case 'semana_acima_limite':
      corpo = (
        <>
          <strong>semana de {formatarData(data, false)}</strong>
          {falta && <> · {falta} acima do limite</>}
        </>
      )
      break
    case 'descanso_semanal_ausente':
      corpo = (
        <>
          <strong>semana de {formatarData(data, false)}</strong>
          {falta && <> · faltaram {falta} de descanso</>}
        </>
      )
      break
    case 'marcacao_invalida':
      corpo = (
        <>
          <strong>{data ? formatarData(data) : 'sem data'}</strong>:{' '}
          {div.detalhe || 'marcação inválida'}
        </>
      )
      break
    case 'total_declarado_divergente':
      corpo = <>{div.detalhe || 'total declarado diverge do recalculado'}</>
      break
    default:
      corpo = (
        <>
          {data && <strong>{formatarData(data)}</strong>} {div.detalhe}{' '}
          {falta && <>· {falta}</>}
        </>
      )
  }
  return <li className={`text-xs leading-relaxed ${MUTED}`}>{corpo}</li>
}

const BlocoGrupo: React.FC<{
  grupo: Grupo
  marcacoes: Map<string, MarcacaoDia>
  dias: Map<string, DiaApurado>
}> = ({ grupo, marcacoes, dias }) => (
  <details
    open={grupo.itens.length <= 6}
    className="group rounded-2xl border border-red-200/80 dark:border-red-900/40 bg-red-50/50 dark:bg-red-950/15 p-4"
  >
    <summary className="flex cursor-pointer list-none items-start gap-3">
      <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-red-800 dark:text-red-300">
          {rotuloTipo(grupo.tipo)}
        </div>
        <div className="text-xs text-red-700 dark:text-red-400 mt-0.5">
          {contagemTipo(grupo.tipo, grupo.itens.length)}
          {grupo.minutos > 0 && <> · total {formatarMinutos(grupo.minutos)}</>}
          {grupo.basesLegais.length > 0 && <> · {grupo.basesLegais.join('; ')}</>}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-red-400 mt-0.5 transition-transform group-open:rotate-90" />
    </summary>
    <ul className="mt-3 ml-7 space-y-1.5 list-disc pl-4 marker:text-red-300">
      {grupo.itens.map((d, i) => (
        <LinhaDivergencia key={`${d.data}-${i}`} div={d} marcacoes={marcacoes} dias={dias} />
      ))}
    </ul>
  </details>
)

/** Painel direito: Documento analisado com paginação e botão Ampliar. */
const PaginaImagem: React.FC<{ documentoId: number }> = ({ documentoId }) => {
  const [info, setInfo] = useState<{ loteId: number; paginas: PaginaDoc[] } | null>(null)
  const [indice, setIndice] = useState(0)
  const [url, setUrl] = useState<string | null>(null)
  const [falhou, setFalhou] = useState(false)
  const [ampliado, setAmpliado] = useState(false)

  useEffect(() => {
    let ativo = true
    apiService
      .getDocumentDetails(documentoId)
      .then((d: { lote_id: number; paginas: PaginaDoc[] }) => {
        if (ativo) setInfo({ loteId: d.lote_id, paginas: d.paginas })
      })
      .catch(() => {
        if (ativo) setFalhou(true)
      })
    return () => {
      ativo = false
    }
  }, [documentoId])

  const numero = info?.paginas[indice]?.numero
  useEffect(() => {
    if (!info || numero === undefined) return
    const controller = new AbortController()
    let objectUrl: string | null = null
    fetchPageImage(info.loteId, numero, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setFalhou(false)
      })
      .catch(() => {
        if (!controller.signal.aborted) setFalhou(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
      setUrl(null)
    }
  }, [info, numero])

  const total = info?.paginas.length ?? 0

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-[11px] font-bold tracking-[0.07em] uppercase text-[#6e6378] dark:text-[#a093a8]">
            DOCUMENTO ANALISADO
          </div>
          <div className="text-sm font-bold text-[#1e1324] dark:text-white mt-0.5">
            {total > 0 ? `Página ${indice + 1} de ${total}` : 'Página 1 de 1'}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {total > 1 && (
            <div className="flex items-center gap-0.5 rounded-xl border border-[#e6dfec] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] p-0.5">
              <button
                type="button"
                aria-label="Página anterior"
                disabled={indice === 0}
                onClick={() => setIndice((i) => i - 1)}
                className="p-1.5 rounded-lg disabled:opacity-30 hover:bg-[#f3e8ff] dark:hover:bg-[#2e1065] text-[#2d0a33] dark:text-white cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                aria-label="Próxima página"
                disabled={indice >= total - 1}
                onClick={() => setIndice((i) => i + 1)}
                className="p-1.5 rounded-lg disabled:opacity-30 hover:bg-[#f3e8ff] dark:hover:bg-[#2e1065] text-[#2d0a33] dark:text-white cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button
            type="button"
            disabled={!url}
            onClick={() => setAmpliado(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold border border-[#e6dfec] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] text-[#1e1324] dark:text-white hover:bg-[#f5eff8] dark:hover:bg-[#26192e] disabled:opacity-40 transition-colors cursor-pointer shadow-2xs"
          >
            <Maximize2 className="w-3.5 h-3.5" />
            <span>Ampliar</span>
          </button>
        </div>
      </div>

      <div className="rounded-2xl border border-[#e3dfe8] dark:border-[#2f1e39] bg-[#e6e5ea] dark:bg-[#110a15] p-4 sm:p-5 min-h-[360px] flex items-center justify-center">
        {url ? (
          <button
            type="button"
            onClick={() => setAmpliado(true)}
            title="Clique para ampliar a página"
            className="block w-full cursor-zoom-in focus:outline-none"
          >
            <img
              src={url}
              alt={`Página ${numero} do documento`}
              className="w-full h-auto rounded-lg shadow-md bg-white"
            />
          </button>
        ) : falhou ? (
          <span className={`text-xs p-4 ${MUTED}`}>Imagem indisponível.</span>
        ) : (
          <Clock className="w-5 h-5 text-[#9333ea] animate-spin" />
        )}
      </div>

      <div className={`flex items-start gap-2 text-xs ${MUTED}`}>
        <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5 text-[#877991]" />
        <span>Dados extraídos automaticamente. Confira o conteúdo no documento original.</span>
      </div>

      {ampliado && url && (
        <div
          className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-xs flex items-center justify-center p-4"
          onClick={() => setAmpliado(false)}
        >
          <div
            className="relative max-w-5xl max-h-[92vh] w-full flex flex-col items-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              type="button"
              onClick={() => setAmpliado(false)}
              aria-label="Fechar visualização ampliada"
              className="self-end mb-2 px-3 py-1.5 rounded-xl bg-white/90 text-[#1e1324] text-xs font-bold flex items-center gap-1.5 hover:bg-white cursor-pointer"
            >
              <X className="w-4 h-4" />
              <span>Fechar</span>
            </button>
            <div className="overflow-auto max-h-[84vh] rounded-xl bg-white p-2 shadow-2xl">
              <img
                src={url}
                alt={`Página ${numero} ampliada`}
                className="max-w-full h-auto"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

const AuditoriaPontoModal: React.FC<Props> = ({ documentoId, filename, onClose }) => {
  const [analise, setAnalise] = useState<AnalisePonto | null>(null)
  const [erroCarga, setErroCarga] = useState<string | null>(null)
  const [recarga, setRecarga] = useState(0)
  const [detalhesAbertos, setDetalhesAbertos] = useState(true)
  const [orientacaoAberta, setOrientacaoAberta] = useState(false)

  const carregar = useCallback(() => {
    setAnalise(null)
    setErroCarga(null)
    setRecarga((n) => n + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    apiService
      .getAnalisePonto(documentoId)
      .then((a: AnalisePonto) => {
        if (ativo) setAnalise(a)
      })
      .catch((e: unknown) => {
        if (ativo)
          setErroCarga(e instanceof Error ? e.message : 'Não foi possível carregar a análise.')
      })
    return () => {
      ativo = false
    }
  }, [documentoId, recarga])

  const marcacoes = useMemo(
    () => new Map((analise?.marcacoes ?? []).map((m) => [m.data, m])),
    [analise]
  )
  const dias = useMemo(
    () => new Map((analise?.totais?.dias ?? []).map((d) => [d.data, d])),
    [analise]
  )
  const grupos = useMemo(() => agruparDivergencias(analise?.divergencias ?? []), [analise])

  const concluida = analise?.estado === 'concluida'
  const risco = analise?.score_geral != null ? Math.round(analise.score_geral * 100) : null
  const nivel = risco != null ? nivelDeRisco(risco) : null
  const britanico = analise?.ponto_britanico
  const diferencas = analise?.diferencas_gemini ?? []

  const dimensoesIndeterminadas = useMemo(() => {
    if (!analise?.scores_dimensao) return []
    return ORDEM_DIMENSOES.filter((chave) => {
      const dim = analise.scores_dimensao?.[chave]
      return !dim || dim.indeterminada || dim.normalizado == null
    })
  }, [analise])

  const semRegistrosSuficientes =
    concluida && (analise?.marcacoes?.length ?? 0) === 0 && (analise?.requer_revisao || risco == null)

  const riscoIndeterminado = risco == null || semRegistrosSuficientes
  const precisaRevisao = Boolean(analise?.requer_revisao || riscoIndeterminado)

  const tituloPrincipal = useMemo(() => {
    if (riscoIndeterminado) return 'Risco ainda não calculado'
    if (nivel === 'baixo') return `Risco baixo (${risco}%)`
    if (nivel === 'medio') return `Risco médio (${risco}%)`
    return `Risco alto (${risco}%)`
  }, [nivel, risco, riscoIndeterminado])

  const subtituloPrincipal = useMemo(() => {
    if (semRegistrosSuficientes) {
      return 'O arquivo não contém registros de ponto suficientes para concluir a auditoria automaticamente.'
    }
    if (risco == null) {
      return 'Alguma dimensão ficou indeterminada e impede o cálculo automático completo.'
    }
    if (analise?.requer_revisao) {
      return 'Alguma dimensão exigiu conferência humana; o percentual exibido representa o risco mínimo identificado.'
    }
    return 'Calculado a partir do maior risco identificado entre as 4 dimensões abaixo.'
  }, [analise?.requer_revisao, risco, semRegistrosSuficientes])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Auditoria de Folha de Ponto"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-6xl bg-[#faf9f6] dark:bg-[#140d18] rounded-3xl border border-[#e9e3ee] dark:border-[#2e1f38] shadow-2xl overflow-hidden max-h-[92vh] flex flex-col"
      >
        {/* Topbar com breadcrumb */}
        <div className="px-6 sm:px-8 py-4 border-b border-[#ece7f0] dark:border-[#281b32] flex items-center justify-between gap-4 bg-white/80 dark:bg-[#1a1120]/90">
          <div className="min-w-0">
            <nav className="flex items-center gap-2 text-xs sm:text-sm text-[#7e7287] dark:text-[#9c8ea6]">
              <span>Auditorias</span>
              <span>&gt;</span>
              <span className="font-semibold text-[#1e1324] dark:text-white">
                Resultado da análise
              </span>
            </nav>
            <p className={`text-xs truncate mt-0.5 ${MUTED}`}>{filename}</p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="p-2 rounded-xl hover:bg-[#f3e8ff] dark:hover:bg-[#2e1065] text-[#6e6378] dark:text-[#a093a8] transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Corpo principal em 2 colunas */}
        <div className="px-6 sm:px-8 py-6 overflow-y-auto grid gap-8 lg:grid-cols-[minmax(0,1fr)_350px] items-start">
          {/* Coluna Esquerda */}
          <div className="space-y-6 min-w-0">
            {!analise && !erroCarga && (
              <div className={`flex items-center gap-2 text-sm py-8 ${MUTED}`}>
                <Clock className="w-4 h-4 text-[#9333ea] animate-spin" /> Carregando a análise...
              </div>
            )}

            {erroCarga && (
              <div className="p-4 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-xs text-red-700 dark:text-red-400">
                {erroCarga}
              </div>
            )}

            {analise?.estado === 'pendente' && (
              <div className="p-5 rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-sm text-amber-800 dark:text-amber-300 space-y-3">
                <p>A análise desta folha ainda não terminou. Tente de novo em instantes.</p>
                <button
                  type="button"
                  onClick={carregar}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-bold bg-amber-500 text-white cursor-pointer"
                >
                  Atualizar
                </button>
              </div>
            )}

            {analise?.estado === 'erro' && (
              <div className="p-5 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-sm text-red-700 dark:text-red-400">
                A análise falhou{analise.erro ? `: ${analise.erro}` : '.'}
              </div>
            )}

            {concluida && (
              <>
                {/* Card Principal de Risco e Detalhes */}
                <div className="p-5 sm:p-6 rounded-2xl bg-white dark:bg-[#1a1120] border border-[#e7e2eb] dark:border-[#2f1e39] shadow-2xs space-y-5">
                  {/* Topo: Anel + Pill + Título + Subtítulo */}
                  <div className="flex flex-col sm:flex-row sm:items-center gap-5">
                    <AnelRisco
                      risco={risco}
                      nivel={nivel}
                      indeterminado={riscoIndeterminado}
                    />

                    <div className="min-w-0 flex-1">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold ${
                          precisaRevisao
                            ? 'bg-[#fef3c7] text-[#92400e] dark:bg-[#382b12] dark:text-amber-300'
                            : nivel === 'baixo'
                              ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'
                              : nivel === 'medio'
                                ? 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300'
                                : 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300'
                        }`}
                      >
                        {precisaRevisao ? (
                          <AlertTriangle className="w-3.5 h-3.5" />
                        ) : (
                          <Check className="w-3.5 h-3.5" />
                        )}
                        <span>
                          {precisaRevisao
                            ? 'Revisão necessária'
                            : nivel
                              ? ROTULO_RISCO[nivel]
                              : 'Indeterminado'}
                        </span>
                      </span>

                      <h3 className="text-xl sm:text-[22px] font-extrabold text-[#1e1324] dark:text-white mt-2 leading-tight">
                        {tituloPrincipal}
                      </h3>
                      <p className="text-xs sm:text-[13px] text-[#5c5166] dark:text-[#b4a7c0] mt-1 leading-relaxed">
                        {subtituloPrincipal}
                      </p>
                    </div>
                  </div>

                  {/* Faixa de alerta humano quando requer revisão */}
                  {precisaRevisao && (
                    <div className="rounded-xl bg-[#fefce8] dark:bg-[#231d11] border border-[#fde68a] dark:border-[#4d3d1a] p-3.5 sm:p-4 space-y-2.5">
                      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <AlertTriangle className="w-4 h-4 text-[#b45309] dark:text-amber-300 shrink-0 mt-0.5" />
                          <div>
                            <div className="text-xs sm:text-[13px] font-bold text-[#78350f] dark:text-amber-200">
                              Uma etapa precisa de conferência humana
                            </div>
                            <p className="text-xs text-[#92400e] dark:text-amber-300/90 mt-0.5">
                              {semRegistrosSuficientes
                                ? 'Confirme se o documento enviado é o arquivo correto antes de tomar qualquer decisão.'
                                : 'Confira as marcações na imagem do documento antes de tomar qualquer decisão.'}
                            </p>
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={() => setOrientacaoAberta((v) => !v)}
                          className="text-xs font-bold text-[#6d28d9] dark:text-[#d8b4fe] hover:underline shrink-0 self-start sm:self-center cursor-pointer"
                        >
                          {orientacaoAberta ? 'Ocultar orientação' : 'Ver orientação'}
                        </button>
                      </div>

                      {orientacaoAberta && (
                        <div className="pt-2.5 border-t border-[#fde68a]/80 dark:border-[#4d3d1a] text-xs text-[#78350f] dark:text-amber-200/90 space-y-1">
                          {dimensoesIndeterminadas.length > 0 ? (
                            <p>
                              Dimensões que exigem conferência manual:{' '}
                              <strong>
                                {dimensoesIndeterminadas
                                  .map((d) => ROTULO_DIMENSAO[d])
                                  .join(', ')}
                              </strong>
                              . Verifique se todas as páginas e colunas de entrada/saída estão
                              legíveis no documento ao lado.
                            </p>
                          ) : (
                            <p>
                              Verifique se o documento corresponde à folha de ponto correta e se as
                              marcações de horário estão completas.
                            </p>
                          )}
                        </div>
                      )}
                    </div>
                  )}

                  {/* Detalhes da análise (colapsável) */}
                  <div className="pt-1 space-y-3">
                    <button
                      type="button"
                      onClick={() => setDetalhesAbertos((v) => !v)}
                      className="w-full flex items-center justify-between text-xs sm:text-[13px] font-bold text-[#1e1324] dark:text-white cursor-pointer"
                    >
                      <span>Detalhes da análise</span>
                      {detalhesAbertos ? (
                        <ChevronUp className="w-4 h-4 text-[#6e6378]" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-[#6e6378]" />
                      )}
                    </button>

                    {detalhesAbertos && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                        {ORDEM_DIMENSOES.map((chave) => {
                          const dim = analise.scores_dimensao?.[chave]
                          const indeterminada =
                            !dim || dim.indeterminada || dim.normalizado == null
                          const pct =
                            !indeterminada && dim?.normalizado != null
                              ? Math.round(dim.normalizado * 100)
                              : null
                          const n = pct != null ? nivelDeRisco(pct) : null

                          const cardStyle = indeterminada
                            ? 'bg-[#fffbeb] border-[#fde68a] dark:bg-[#241c11] dark:border-[#4d3d1a]'
                            : n === 'alto'
                              ? 'bg-[#fef2f2] border-[#fecaca] dark:bg-[#26141c] dark:border-[#4c1d2b]'
                              : n === 'medio'
                                ? 'bg-[#fffbeb] border-[#fde68a] dark:bg-[#241c11] dark:border-[#4d3d1a]'
                                : 'bg-[#f9f9fb] border-[#ebe5ef] dark:bg-[#150c18] dark:border-[#2f1e39]'

                          const valorTexto = indeterminada ? 'Indeterminado' : `${pct}%`
                          const valorCor = indeterminada
                            ? 'text-sm sm:text-[15px] font-extrabold text-[#b45309] dark:text-amber-300'
                            : `text-lg sm:text-xl font-extrabold ${
                                n ? COR_TEXTO[n] : 'text-[#1e1324] dark:text-white'
                              }`

                          const subtexto = indeterminada
                            ? 'Exige conferência'
                            : n === 'baixo'
                              ? 'Dentro do limite'
                              : n === 'medio'
                                ? 'Atenção'
                                : 'Acima do limite'

                          return (
                            <div
                              key={chave}
                              className={`p-3.5 rounded-xl border flex flex-col justify-between min-h-[104px] ${cardStyle}`}
                            >
                              <div className="flex items-start justify-between gap-1.5">
                                <span className="text-xs font-medium text-[#5c5166] dark:text-[#b4a7c0] leading-tight">
                                  {ROTULO_DIMENSAO[chave]}
                                </span>
                                {!indeterminada && n === 'baixo' && (
                                  <span className="w-4 h-4 rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                                    <Check className="w-2.5 h-2.5 stroke-[3]" />
                                  </span>
                                )}
                                {!indeterminada && (n === 'medio' || n === 'alto') && (
                                  <AlertTriangle
                                    className={`w-3.5 h-3.5 shrink-0 ${
                                      n === 'alto' ? 'text-red-500' : 'text-amber-500'
                                    }`}
                                  />
                                )}
                              </div>

                              <div className={`my-2 ${valorCor}`}>{valorTexto}</div>

                              <div className="text-[11px] text-[#6e6378] dark:text-[#9c8ea6]">
                                {subtexto}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </div>

                {/* Nota de apoio jurídico */}
                <div className={`flex items-start gap-2 text-xs ${MUTED}`}>
                  <Info className="w-4 h-4 shrink-0 mt-0.5 text-[#877991]" />
                  <span>
                    Esta análise serve como apoio e não substitui parecer jurídico. A convenção
                    coletiva pode alterar os limites usados aqui.
                  </span>
                </div>

                {/* Bloco 1: RESULTADO OBJETIVO / Divergências identificadas */}
                <div className="space-y-3">
                  <div className="flex items-center gap-3">
                    <span className="w-7 h-7 rounded-lg bg-[#f3e8ff] dark:bg-[#2e1065] text-[#6d28d9] dark:text-[#d8b4fe] text-xs font-extrabold flex items-center justify-center shrink-0">
                      1
                    </span>
                    <div>
                      <div className="text-[10px] font-bold tracking-[0.08em] uppercase text-[#6e6378] dark:text-[#a093a8]">
                        RESULTADO OBJETIVO
                      </div>
                      <h4 className="text-base font-bold text-[#1e1324] dark:text-white leading-tight">
                        Divergências identificadas
                      </h4>
                    </div>
                  </div>

                  {grupos.length > 0 ? (
                    <div className="space-y-2.5">
                      {grupos.map((g) => (
                        <BlocoGrupo
                          key={g.tipo}
                          grupo={g}
                          marcacoes={marcacoes}
                          dias={dias}
                        />
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-start gap-3 p-4 rounded-2xl border border-[#bbf7d0] dark:border-[#184634] bg-[#f0fdf4] dark:bg-[#0d261d]">
                      <span className="w-6 h-6 rounded-full bg-emerald-700 dark:bg-emerald-600 text-white flex items-center justify-center shrink-0 mt-0.5">
                        <Check className="w-3.5 h-3.5 stroke-[3]" />
                      </span>
                      <div>
                        <div className="text-xs sm:text-[13px] font-bold text-[#064e3b] dark:text-emerald-200">
                          Nenhuma divergência encontrada
                        </div>
                        <p className="text-xs text-[#047857] dark:text-emerald-300/90 mt-0.5">
                          Não há ocorrências fora dos limites nas informações que puderam ser lidas.
                        </p>
                      </div>
                    </div>
                  )}

                  {britanico?.conclusivo && britanico.sinal_risco && (
                    <div className="p-4 rounded-2xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-xs text-amber-800 dark:text-amber-300 space-y-1">
                      <div className="font-bold">Sinal de risco: ponto britânico</div>
                      <p>
                        {britanico.fracao_uniforme != null
                          ? `${Math.round(britanico.fracao_uniforme * 100)}% dos dias têm horários praticamente idênticos. `
                          : 'Horários praticamente idênticos ao longo do período. '}
                        É um indício para conferir, não é prova de fraude.
                      </p>
                    </div>
                  )}

                  {diferencas.length > 0 && (
                    <p className={`text-xs ${MUTED}`}>
                      {diferencas.length}{' '}
                      {diferencas.length === 1 ? 'valor divergiu' : 'valores divergiram'} da
                      leitura do Gemini; vale o cálculo do código.
                    </p>
                  )}
                </div>

                {/* Bloco 2: INTERPRETAÇÃO DA IA / Parecer da auditoria */}
                {analise.analise && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-3">
                      <span className="w-7 h-7 rounded-lg bg-[#f3e8ff] dark:bg-[#2e1065] text-[#6d28d9] dark:text-[#d8b4fe] text-xs font-extrabold flex items-center justify-center shrink-0">
                        2
                      </span>
                      <div>
                        <div className="text-[10px] font-bold tracking-[0.08em] uppercase text-[#6e6378] dark:text-[#a093a8]">
                          INTERPRETAÇÃO DA IA
                        </div>
                        <h4 className="text-base font-bold text-[#1e1324] dark:text-white leading-tight">
                          Parecer da auditoria
                        </h4>
                      </div>
                    </div>

                    <div className="p-4 rounded-2xl border border-[#e7dff0] dark:border-[#2f1e39] bg-[#f8f5fc] dark:bg-[#191021] flex items-start gap-3">
                      <FileText className="w-4 h-4 text-[#7e7287] dark:text-[#a093a8] shrink-0 mt-0.5" />
                      <p className="text-xs sm:text-[13.5px] text-[#2d0a33] dark:text-[#f1eaf6] leading-relaxed">
                        {analise.analise}
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Coluna Direita: Documento analisado */}
          <PaginaImagem documentoId={documentoId} />
        </div>
      </div>
    </div>
  )
}

export default AuditoriaPontoModal
