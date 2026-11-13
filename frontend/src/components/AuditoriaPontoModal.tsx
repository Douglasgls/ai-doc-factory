import React, { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Clock,
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
  rotuloSemValor,
  rotuloTipo,
  textoBaseRisco,
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
  baixo: 'text-emerald-600 dark:text-emerald-400',
  medio: 'text-amber-600 dark:text-amber-400',
  alto: 'text-red-600 dark:text-red-400',
}

const MUTED = 'text-[#7b6f85] dark:text-[#9c8ea6]'

const faixaMarcas = (m: MarcacaoDia): string =>
  m.pares.map(([e, s]) => `${formatarMarca(e)}–${formatarMarca(s)}`).join('  ·  ')

/** Anel circular minimalista de risco. */
const AnelRisco: React.FC<{
  risco: number | null
  nivel: NivelRisco | null
  indeterminado: boolean
}> = ({ risco, nivel, indeterminado }) => {
  const raio = 34
  const circunferencia = 2 * Math.PI * raio
  const percentual =
    indeterminado || risco == null ? 28 : Math.max(0, Math.min(100, risco))
  const offset =
    !indeterminado && risco === 0
      ? 0
      : circunferencia - (percentual / 100) * circunferencia

  const corTrajeto =
    indeterminado || nivel == null
      ? '#d97706'
      : nivel === 'baixo'
        ? '#10b981'
        : nivel === 'medio'
          ? '#f59e0b'
          : '#ef4444'

  const corTrilha =
    indeterminado || nivel == null
      ? 'stroke-amber-100 dark:stroke-amber-950/50'
      : nivel === 'baixo'
        ? 'stroke-emerald-100 dark:stroke-emerald-950/50'
        : nivel === 'medio'
          ? 'stroke-amber-100 dark:stroke-amber-950/50'
          : 'stroke-red-100 dark:stroke-red-950/50'

  return (
    <div
      className="relative w-20 h-20 shrink-0 flex items-center justify-center"
      role="img"
      aria-label={
        indeterminado || risco == null
          ? 'Risco ainda não calculado'
          : `Risco de ${risco}%`
      }
    >
      <svg className="w-full h-full -rotate-90" viewBox="0 0 84 84" aria-hidden="true">
        <circle
          cx="42"
          cy="42"
          r={raio}
          fill="none"
          strokeWidth="5.5"
          className={corTrilha}
        />
        <circle
          cx="42"
          cy="42"
          r={raio}
          fill="none"
          strokeWidth="5.5"
          strokeLinecap="round"
          stroke={corTrajeto}
          strokeDasharray={circunferencia}
          strokeDashoffset={offset}
          className="transition-all duration-500"
        />
      </svg>
      <span
        className={`absolute font-bold ${
          indeterminado || risco == null
            ? 'text-lg text-amber-700 dark:text-amber-300'
            : `text-base ${nivel ? COR_TEXTO[nivel] : 'text-[#1e1324] dark:text-white'}`
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
    open={grupo.itens.length <= 5}
    className="group rounded-xl border border-red-200/70 dark:border-red-900/40 bg-red-50/40 dark:bg-red-950/10 p-3.5"
  >
    <summary className="flex cursor-pointer list-none items-center gap-3">
      <AlertTriangle className="w-4 h-4 text-red-500 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-red-900 dark:text-red-300">
          {rotuloTipo(grupo.tipo)}
        </div>
        <div className="text-xs text-red-700/80 dark:text-red-400/90 mt-0.5">
          {contagemTipo(grupo.tipo, grupo.itens.length)}
          {grupo.minutos > 0 && <> · {formatarMinutos(grupo.minutos)}</>}
          {grupo.basesLegais.length > 0 && <> · {grupo.basesLegais.join('; ')}</>}
        </div>
      </div>
      <ChevronRight className="w-4 h-4 text-red-400 transition-transform group-open:rotate-90" />
    </summary>
    <ul className="mt-3 ml-7 space-y-1.5 list-disc pl-4 marker:text-red-300">
      {grupo.itens.map((d, i) => (
        <LinhaDivergencia key={`${d.data}-${i}`} div={d} marcacoes={marcacoes} dias={dias} />
      ))}
    </ul>
  </details>
)

/** Painel direito: Visualização limpa da página do documento. */
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
    <div className="space-y-3 lg:sticky lg:top-0">
      <div className="flex items-center justify-between gap-2">
        <div>
          <span className="text-[10px] font-bold tracking-[0.08em] uppercase text-[#8a7e94]">
            Documento
          </span>
          <div className="text-xs font-semibold text-[#1e1324] dark:text-white">
            {total > 0 ? `Página ${indice + 1} de ${total}` : 'Página 1 de 1'}
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {total > 1 && (
            <div className="flex items-center rounded-lg border border-[#e7e2eb] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120]">
              <button
                type="button"
                aria-label="Página anterior"
                disabled={indice === 0}
                onClick={() => setIndice((i) => i - 1)}
                className="p-1.5 disabled:opacity-30 hover:text-[#9333ea] text-[#4e4356] dark:text-[#c7bad1] cursor-pointer"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                aria-label="Próxima página"
                disabled={indice >= total - 1}
                onClick={() => setIndice((i) => i + 1)}
                className="p-1.5 disabled:opacity-30 hover:text-[#9333ea] text-[#4e4356] dark:text-[#c7bad1] cursor-pointer"
              >
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          <button
            type="button"
            disabled={!url}
            onClick={() => setAmpliado(true)}
            className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border border-[#e7e2eb] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] text-[#1e1324] dark:text-white hover:bg-[#f7f4f9] dark:hover:bg-[#26192e] disabled:opacity-40 transition-colors cursor-pointer"
          >
            <Maximize2 className="w-3.5 h-3.5 text-[#7b6f85]" />
            <span>Ampliar</span>
          </button>
        </div>
      </div>

      <div className="rounded-2xl bg-[#efedf2] dark:bg-[#100a14] p-3.5 min-h-[340px] flex items-center justify-center">
        {url ? (
          <button
            type="button"
            onClick={() => setAmpliado(true)}
            title="Clique para ampliar"
            className="block w-full cursor-zoom-in focus:outline-none"
          >
            <img
              src={url}
              alt={`Página ${numero} do documento`}
              className="w-full h-auto rounded-lg shadow-sm bg-white"
            />
          </button>
        ) : falhou ? (
          <span className={`text-xs p-4 ${MUTED}`}>Imagem indisponível.</span>
        ) : (
          <Clock className="w-5 h-5 text-[#9333ea] animate-spin" />
        )}
      </div>

      <div className={`flex items-center gap-1.5 text-[11px] ${MUTED}`}>
        <ShieldCheck className="w-3.5 h-3.5 shrink-0" />
        <span>Confira os horários diretamente no documento original.</span>
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
              className="self-end mb-2 px-3 py-1.5 rounded-xl bg-white/95 text-[#1e1324] text-xs font-semibold flex items-center gap-1.5 hover:bg-white cursor-pointer"
            >
              <X className="w-4 h-4" />
              <span>Fechar</span>
            </button>
            <div className="overflow-auto max-h-[84vh] rounded-xl bg-white p-2 shadow-2xl">
              <img src={url} alt={`Página ${numero} ampliada`} className="max-w-full h-auto" />
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
      return !dim?.nao_avaliada && (!dim || dim.indeterminada || dim.normalizado == null)
    })
  }, [analise])

  const semRegistrosSuficientes =
    concluida &&
    (analise?.marcacoes?.length ?? 0) === 0 &&
    (analise?.requer_revisao || risco == null)

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
      return 'O arquivo não contém registros de ponto suficientes para concluir a auditoria.'
    }
    if (risco == null) {
      return 'Alguma dimensão ficou indeterminada e impede o cálculo automático completo.'
    }
    const base = textoBaseRisco(analise?.scores_dimensao)
    if (analise?.requer_revisao) {
      return `O percentual é um piso; recomenda-se conferência. ${base}`
    }
    return base
  }, [analise?.requer_revisao, analise?.scores_dimensao, risco, semRegistrosSuficientes])

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/55 backdrop-blur-xs animate-in fade-in duration-150"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Auditoria de Folha de Ponto"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl bg-white dark:bg-[#17101c] rounded-3xl border border-[#ece7f0] dark:border-[#2c1e36] shadow-2xl overflow-hidden max-h-[92vh] flex flex-col"
      >
        {/* Cabeçalho limpo */}
        <div className="px-6 sm:px-8 py-4 border-b border-[#f0ecf4] dark:border-[#261a2e] flex items-center justify-between gap-4">
          <div className="min-w-0 flex items-center gap-2 text-xs sm:text-sm">
            <span className="text-[#8a7e94]">Auditorias</span>
            <span className="text-[#c5bccd] dark:text-[#4e3d5c]">/</span>
            <span className="font-semibold text-[#1e1324] dark:text-white truncate">
              {filename}
            </span>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={onClose}
            className="p-1.5 rounded-xl hover:bg-[#f5f1f8] dark:hover:bg-[#26192e] text-[#7b6f85] dark:text-[#a093a8] transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Corpo em 2 colunas com bastante respiro */}
        <div className="px-6 sm:px-8 py-6 overflow-y-auto grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px] items-start">
          {/* Coluna Esquerda */}
          <div className="space-y-7 min-w-0">
            {!analise && !erroCarga && (
              <div className={`flex items-center gap-2.5 text-sm py-10 ${MUTED}`}>
                <Clock className="w-4 h-4 text-[#9333ea] animate-spin" />
                <span>Carregando resultado da análise...</span>
              </div>
            )}

            {erroCarga && (
              <div className="p-4 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50/70 dark:bg-red-950/20 text-xs text-red-700 dark:text-red-400">
                {erroCarga}
              </div>
            )}

            {analise?.estado === 'pendente' && (
              <div className="p-5 rounded-2xl bg-amber-50/70 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-900/40 text-sm text-amber-900 dark:text-amber-300 flex items-center justify-between gap-4">
                <span>A análise desta folha ainda está em processamento.</span>
                <button
                  type="button"
                  onClick={carregar}
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-amber-500 text-white hover:bg-amber-600 cursor-pointer shrink-0"
                >
                  Atualizar
                </button>
              </div>
            )}

            {analise?.estado === 'erro' && (
              <div className="p-5 rounded-2xl bg-red-50/70 dark:bg-red-950/20 border border-red-200/80 dark:border-red-900/40 text-sm text-red-700 dark:text-red-400">
                A análise falhou{analise.erro ? `: ${analise.erro}` : '.'}
              </div>
            )}

            {concluida && (
              <>
                {/* Resumo Principal */}
                <section className="space-y-5">
                  <div className="flex flex-col sm:flex-row sm:items-center gap-5">
                    <AnelRisco
                      risco={risco}
                      nivel={nivel}
                      indeterminado={riscoIndeterminado}
                    />

                    <div className="min-w-0 flex-1 space-y-1.5">
                      <span
                        className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold ${
                          precisaRevisao
                            ? 'bg-amber-100/80 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                            : nivel === 'baixo'
                              ? 'bg-emerald-100/80 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300'
                              : nivel === 'medio'
                                ? 'bg-amber-100/80 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300'
                                : 'bg-red-100/80 text-red-800 dark:bg-red-950/50 dark:text-red-300'
                        }`}
                      >
                        {precisaRevisao ? (
                          <AlertTriangle className="w-3 h-3" />
                        ) : (
                          <Check className="w-3 h-3" />
                        )}
                        <span>
                          {precisaRevisao
                            ? 'Revisão necessária'
                            : nivel
                              ? ROTULO_RISCO[nivel]
                              : 'Indeterminado'}
                        </span>
                      </span>

                      <h3 className="text-xl font-bold text-[#1e1324] dark:text-white leading-snug">
                        {tituloPrincipal}
                      </h3>
                      <p className={`text-xs sm:text-[13px] leading-relaxed ${MUTED}`}>
                        {subtituloPrincipal}
                      </p>
                    </div>
                  </div>

                  {/* Alerta enxuto de conferência */}
                  {precisaRevisao && (
                    <div className="rounded-xl bg-amber-50/70 dark:bg-amber-950/20 px-4 py-3 space-y-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2.5 text-xs text-amber-900 dark:text-amber-200">
                          <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
                          <span className="font-medium">
                            {semRegistrosSuficientes
                              ? 'Confirme se o documento enviado é uma folha de ponto válida.'
                              : 'Uma dimensão exige conferência humana nos horários.'}
                          </span>
                        </div>

                        <button
                          type="button"
                          onClick={() => setOrientacaoAberta((v) => !v)}
                          className="text-xs font-semibold text-[#7e22ce] dark:text-[#d8b4fe] hover:underline shrink-0 cursor-pointer"
                        >
                          {orientacaoAberta ? 'Ocultar' : 'Ver orientação'}
                        </button>
                      </div>

                      {orientacaoAberta && (
                        <p className="text-xs text-amber-800/90 dark:text-amber-300/90 pl-6 leading-relaxed">
                          {dimensoesIndeterminadas.length > 0
                            ? `Dimensões sem dados conclusivos: ${dimensoesIndeterminadas
                                .map((d) => ROTULO_DIMENSAO[d])
                                .join(', ')}. Verifique se o arquivo corresponde ao período e se os horários estão legíveis.`
                            : 'Verifique na imagem ao lado se todas as marcações de entrada e saída foram capturadas.'}
                        </p>
                      )}
                    </div>
                  )}

                  {/* 4 Dimensões — layout limpo e minimalista */}
                  <div className="pt-1">
                    <button
                      type="button"
                      onClick={() => setDetalhesAbertos((v) => !v)}
                      className="w-full flex items-center justify-between text-xs font-semibold text-[#4e4356] dark:text-[#c7bad1] mb-3 cursor-pointer"
                    >
                      <span>Dimensões avaliadas</span>
                      {detalhesAbertos ? (
                        <ChevronUp className="w-4 h-4 text-[#8a7e94]" />
                      ) : (
                        <ChevronDown className="w-4 h-4 text-[#8a7e94]" />
                      )}
                    </button>

                    {detalhesAbertos && (
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                        {ORDEM_DIMENSOES.map((chave) => {
                          const dim = analise.scores_dimensao?.[chave]
                          const naoAvaliada = Boolean(dim?.nao_avaliada)
                          const indeterminada =
                            !naoAvaliada && (!dim || dim.indeterminada || dim.normalizado == null)
                          const pct =
                            !naoAvaliada && !indeterminada && dim?.normalizado != null
                              ? Math.round(dim.normalizado * 100)
                              : null
                          const n = pct != null ? nivelDeRisco(pct) : null

                          const cardBg = indeterminada
                            ? 'bg-amber-50/60 dark:bg-amber-950/20 border-amber-200/70 dark:border-amber-900/40'
                            : n === 'alto'
                              ? 'bg-red-50/60 dark:bg-red-950/20 border-red-200/70 dark:border-red-900/40'
                              : n === 'medio'
                                ? 'bg-amber-50/60 dark:bg-amber-950/20 border-amber-200/70 dark:border-amber-900/40'
                                : 'bg-[#f8f6fa] dark:bg-[#1e1525] border-transparent dark:border-[#2a1d35]'

                          return (
                            <div
                              key={chave}
                              className={`p-3 rounded-xl border flex flex-col justify-between min-h-[88px] ${cardBg}`}
                            >
                              <div className="flex items-center justify-between gap-1">
                                <span className={`text-[11px] font-medium ${MUTED}`}>
                                  {ROTULO_DIMENSAO[chave]}
                                </span>
                                {!naoAvaliada && !indeterminada && n === 'baixo' && (
                                  <Check className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                                )}
                              </div>

                              <div
                                className={`my-1 font-bold ${
                                  naoAvaliada
                                    ? 'text-xs text-[#6e6378] dark:text-[#a093a8]'
                                    : indeterminada
                                      ? 'text-xs text-amber-700 dark:text-amber-300'
                                      : `text-lg ${
                                          n ? COR_TEXTO[n] : 'text-[#1e1324] dark:text-white'
                                        }`
                                }`}
                              >
                                {naoAvaliada || indeterminada ? rotuloSemValor(dim) : `${pct}%`}
                              </div>

                              <div className="text-[10px] text-[#8a7e94]">
                                {naoAvaliada
                                  ? dim?.motivo === 'sem_semana_completa'
                                    ? 'Sem semana completa'
                                    : 'Dados insuficientes'
                                  : indeterminada
                                    ? 'Exige conferência'
                                    : n === 'baixo'
                                      ? 'Dentro do limite'
                                      : n === 'medio'
                                        ? 'Atenção'
                                        : 'Acima do limite'}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    )}
                  </div>
                </section>

                <hr className="border-[#f0ecf4] dark:border-[#261a2e]" />

                {/* Seção 1: Divergências */}
                <section className="space-y-3">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-md bg-[#f3e8ff] dark:bg-[#2e1065] text-[#6d28d9] dark:text-[#d8b4fe] text-xs font-bold flex items-center justify-center">
                      1
                    </span>
                    <h4 className="text-sm font-bold text-[#1e1324] dark:text-white">
                      Divergências identificadas
                    </h4>
                  </div>

                  {grupos.length > 0 ? (
                    <div className="space-y-2">
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
                    <div className="flex items-center gap-3 p-3.5 rounded-xl bg-emerald-50/60 dark:bg-emerald-950/20">
                      <span className="w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0">
                        <Check className="w-3 h-3 stroke-[3]" />
                      </span>
                      <div className="text-xs">
                        <span className="font-semibold text-emerald-900 dark:text-emerald-200">
                          Nenhuma divergência encontrada.{' '}
                        </span>
                        <span className="text-emerald-700/90 dark:text-emerald-300/80">
                          Sem ocorrências fora dos limites nos dados lidos.
                        </span>
                      </div>
                    </div>
                  )}

                  {britanico?.conclusivo && britanico.sinal_risco && (
                    <div className="p-3.5 rounded-xl bg-amber-50/70 dark:bg-amber-950/20 text-xs text-amber-900 dark:text-amber-300">
                      <span className="font-semibold">Sinal de ponto britânico: </span>
                      {britanico.fracao_uniforme != null
                        ? `${Math.round(britanico.fracao_uniforme * 100)}% dos dias têm horários praticamente idênticos.`
                        : 'Horários praticamente idênticos ao longo do período.'}
                    </div>
                  )}

                  {diferencas.length > 0 && (
                    <p className={`text-xs ${MUTED}`}>
                      {diferencas.length}{' '}
                      {diferencas.length === 1 ? 'valor divergiu' : 'valores divergiram'} da
                      leitura da IA; prevalece o cálculo do sistema.
                    </p>
                  )}
                </section>

                {/* Seção 2: Parecer da auditoria */}
                {analise.analise && (
                  <section className="space-y-3">
                    <div className="flex items-center gap-2.5">
                      <span className="w-6 h-6 rounded-md bg-[#f3e8ff] dark:bg-[#2e1065] text-[#6d28d9] dark:text-[#d8b4fe] text-xs font-bold flex items-center justify-center">
                        2
                      </span>
                      <h4 className="text-sm font-bold text-[#1e1324] dark:text-white">
                        Parecer da auditoria
                      </h4>
                    </div>

                    <p className="p-4 rounded-xl bg-[#f8f6fa] dark:bg-[#1e1525] text-xs sm:text-[13px] text-[#3a2c44] dark:text-[#e5dff0] leading-relaxed">
                      {analise.analise}
                    </p>
                  </section>
                )}
              </>
            )}
          </div>

          {/* Coluna Direita: Documento analisado */}
          <PaginaImagem documentoId={documentoId} />
        </div>

        {/* Rodapé discreto */}
        <div className="px-6 sm:px-8 py-3 border-t border-[#f0ecf4] dark:border-[#261a2e] flex items-center justify-between gap-4 text-[11px] text-[#8a7e94]">
          <span className="flex items-center gap-1.5">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>
              Apoio à auditoria, não substitui parecer jurídico. Convenções coletivas podem alterar os
              limites.
            </span>
          </span>
        </div>
      </div>
    </div>
  )
}

export default AuditoriaPontoModal
