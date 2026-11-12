import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, ChevronLeft, ChevronRight, Clock, Info, X } from 'lucide-react'
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
  textoBaseRisco,
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

const COR_FUNDO: Record<NivelRisco, string> = {
  baixo: 'bg-emerald-500',
  medio: 'bg-amber-500',
  alto: 'bg-red-500',
}
const COR_TEXTO: Record<NivelRisco, string> = {
  baixo: 'text-emerald-700 dark:text-emerald-400',
  medio: 'text-amber-700 dark:text-amber-400',
  alto: 'text-red-700 dark:text-red-400',
}

const TITULO_SECAO = 'text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider'
const MUTED = 'text-[#6e6378] dark:text-[#a093a8]'

const faixaMarcas = (m: MarcacaoDia): string =>
  m.pares.map(([e, s]) => `${formatarMarca(e)}–${formatarMarca(s)}`).join('  ·  ')

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
      const lacunas = marc ? marc.pares.slice(0, -1).map((p, i) => [p[1], marc.pares[i + 1][0]] as const) : []
      corpo = (
        <>
          <strong>{formatarData(data)}</strong>:{' '}
          {!marc ? (
            indisponivel
          ) : lacunas.length === 0 ? (
            <>sem intervalo registrado (jornada de {faixaMarcas(marc)})</>
          ) : (
            <>
              {lacunas.map(([s, r]) => `saída ${formatarMarca(s)}, retorno ${formatarMarca(r)}`).join(' · ')}
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
              <strong>saída {formatarData(anterior, false)} {formatarMarca(saida)}</strong> → <strong>entrada {formatarData(data, false)} {formatarMarca(entrada)}</strong>
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
          <strong>{data ? formatarData(data) : 'sem data'}</strong>: {div.detalhe || 'marcação inválida'}
        </>
      )
      break
    case 'total_declarado_divergente':
      corpo = <>{div.detalhe || 'total declarado diverge do recalculado'}</>
      break
    default:
      corpo = (
        <>
          {data && <strong>{formatarData(data)}</strong>} {div.detalhe} {falta && <>· {falta}</>}
        </>
      )
  }
  return <li className={`text-xs leading-relaxed ${MUTED}`}>{corpo}</li>
}

const BlocoGrupo: React.FC<{ grupo: Grupo; marcacoes: Map<string, MarcacaoDia>; dias: Map<string, DiaApurado> }> = ({
  grupo,
  marcacoes,
  dias,
}) => (
  <details
    open={grupo.itens.length <= 6}
    className="group rounded-xl border border-red-100 dark:border-red-900/30 bg-red-50/50 dark:bg-red-950/10 p-3"
  >
    <summary className="flex cursor-pointer list-none items-start gap-3">
      <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold text-red-800 dark:text-red-300">{rotuloTipo(grupo.tipo)}</div>
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

/** Imagem da página do documento (rota autenticada: fetch + object URL, revogado ao trocar de página ou fechar). */
const PaginaImagem: React.FC<{ documentoId: number }> = ({ documentoId }) => {
  const [info, setInfo] = useState<{ loteId: number; paginas: PaginaDoc[] } | null>(null)
  const [indice, setIndice] = useState(0)
  const [url, setUrl] = useState<string | null>(null)
  const [falhou, setFalhou] = useState(false)

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
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <h4 className={TITULO_SECAO}>Página do documento</h4>
        {total > 1 && (
          <div className="flex items-center gap-1 text-xs">
            <button
              type="button"
              aria-label="Página anterior"
              disabled={indice === 0}
              onClick={() => setIndice((i) => i - 1)}
              className="p-1 rounded-lg disabled:opacity-30 hover:bg-[#f3e8ff] dark:hover:bg-[#2e1065] cursor-pointer"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <span className={MUTED}>
              {indice + 1} de {total}
            </span>
            <button
              type="button"
              aria-label="Próxima página"
              disabled={indice >= total - 1}
              onClick={() => setIndice((i) => i + 1)}
              className="p-1 rounded-lg disabled:opacity-30 hover:bg-[#f3e8ff] dark:hover:bg-[#2e1065] cursor-pointer"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
      <div className="rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-[#f8f5fa] dark:bg-[#150c18] min-h-48 flex items-center justify-center overflow-hidden">
        {url ? (
          <a href={url} target="_blank" rel="noreferrer" title="Abrir a página em tamanho real" className="block w-full">
            <img src={url} alt={`Página ${numero} do documento`} className="w-full h-auto" />
          </a>
        ) : falhou ? (
          <span className={`text-xs p-4 ${MUTED}`}>Imagem indisponível.</span>
        ) : (
          <Clock className="w-5 h-5 text-[#9333ea] animate-spin" />
        )}
      </div>
      <p className={`text-[10px] ${MUTED}`}>Os horários vêm da leitura do Gemini e podem ter erro: confira na imagem.</p>
    </div>
  )
}

const AuditoriaPontoModal: React.FC<Props> = ({ documentoId, filename, onClose }) => {
  const [analise, setAnalise] = useState<AnalisePonto | null>(null)
  const [erroCarga, setErroCarga] = useState<string | null>(null)
  const [recarga, setRecarga] = useState(0)

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
        if (ativo) setErroCarga(e instanceof Error ? e.message : 'Não foi possível carregar a análise.')
      })
    return () => {
      ativo = false
    }
  }, [documentoId, recarga])

  const marcacoes = useMemo(() => new Map((analise?.marcacoes ?? []).map((m) => [m.data, m])), [analise])
  const dias = useMemo(() => new Map((analise?.totais?.dias ?? []).map((d) => [d.data, d])), [analise])
  const grupos = useMemo(() => agruparDivergencias(analise?.divergencias ?? []), [analise])

  const concluida = analise?.estado === 'concluida'
  const risco = analise?.score_geral != null ? Math.round(analise.score_geral * 100) : null
  const nivel = risco != null ? nivelDeRisco(risco) : null
  const britanico = analise?.ponto_britanico
  const diferencas = analise?.diferencas_gemini ?? []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Auditoria de Folha de Ponto"
        className="w-full max-w-5xl bg-white dark:bg-[#1a1120] rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
      >
        <div className="p-6 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between bg-[#fbf9fc] dark:bg-[#1f1325]">
          <div className="min-w-0">
            <h3 className="text-lg font-bold text-[#2d0a33] dark:text-[#f8f5fc]">Auditoria de Folha de Ponto</h3>
            <p className={`text-xs truncate ${MUTED}`}>{filename}</p>
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

        <div className="p-6 overflow-y-auto grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
          <div className="space-y-6 min-w-0">
            {!analise && !erroCarga && (
              <div className={`flex items-center gap-2 text-sm ${MUTED}`}>
                <Clock className="w-4 h-4 text-[#9333ea] animate-spin" /> Carregando a análise...
              </div>
            )}
            {erroCarga && (
              <div className="p-3 rounded-xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-xs text-red-700 dark:text-red-400">
                {erroCarga}
              </div>
            )}
            {analise?.estado === 'pendente' && (
              <div className="p-4 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-sm text-amber-800 dark:text-amber-300 space-y-2">
                <p>A análise desta folha ainda não terminou. Tente de novo em instantes.</p>
                <button
                  type="button"
                  onClick={carregar}
                  className="px-3 py-1 rounded-lg text-xs font-bold bg-amber-500 text-white cursor-pointer"
                >
                  Atualizar
                </button>
              </div>
            )}
            {analise?.estado === 'erro' && (
              <div className="p-4 rounded-xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-sm text-red-700 dark:text-red-400">
                A análise falhou{analise.erro ? `: ${analise.erro}` : '.'}
              </div>
            )}

            {concluida && (
              <>
                {/* Risco da folha: 0 a 1, maior é pior */}
                <div className="p-4 rounded-2xl bg-[#f8f5fa] dark:bg-[#201326] border border-[#ece4f1] dark:border-[#382240] space-y-4">
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-16 h-16 rounded-full flex items-center justify-center text-white font-bold shrink-0 ${
                        nivel ? COR_FUNDO[nivel] : 'bg-slate-400 dark:bg-slate-600'
                      } ${risco != null ? 'text-lg' : 'text-[10px] text-center leading-tight px-1'}`}
                    >
                      {risco != null ? `${risco}%` : 'N/D'}
                    </div>
                    <div>
                      <div className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc]">Risco da folha</div>
                      <div className={`text-sm font-semibold ${nivel ? COR_TEXTO[nivel] : MUTED}`}>
                        {nivel ? ROTULO_RISCO[nivel] : 'Indeterminado'}
                      </div>
                      <div className={`text-[10px] ${MUTED}`}>
                        Quanto maior, pior. {textoBaseRisco(analise.scores_dimensao)}
                      </div>
                    </div>
                  </div>

                  {analise.requer_revisao && (
                    <div className="flex items-start gap-2 p-2.5 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/40 text-xs text-amber-800 dark:text-amber-300">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <span>Alguma dimensão ficou indeterminada e precisa de conferência humana. O risco geral é um piso.</span>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-2">
                    {ORDEM_DIMENSOES.map((chave) => {
                      const dim = analise.scores_dimensao?.[chave]
                      const pct = dim && !dim.indeterminada && dim.normalizado != null ? Math.round(dim.normalizado * 100) : null
                      const n = pct != null ? nivelDeRisco(pct) : null
                      return (
                        <div
                          key={chave}
                          className="p-2.5 rounded-xl bg-white dark:bg-[#150c18] border border-[#ece4f1] dark:border-[#382240]"
                        >
                          <div className={`text-[10px] ${MUTED}`}>{ROTULO_DIMENSAO[chave]}</div>
                          <div className={`text-sm font-bold ${n ? COR_TEXTO[n] : MUTED}`}>
                            {pct != null ? `${pct}%` : rotuloSemValor(dim)}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                <div className={`flex items-start gap-2 text-[10px] ${MUTED}`}>
                  <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
                  <span>
                    Apoio à auditoria, não é parecer jurídico. Convenção coletiva e acordo de compensação podem alterar os
                    limites usados aqui.
                  </span>
                </div>

                {/* Divergências agrupadas por tipo */}
                <div className="space-y-3">
                  <h4 className={TITULO_SECAO}>Divergências identificadas</h4>
                  {grupos.length > 0 ? (
                    <div className="space-y-2">
                      {grupos.map((g) => (
                        <BlocoGrupo key={g.tipo} grupo={g} marcacoes={marcacoes} dias={dias} />
                      ))}
                    </div>
                  ) : (
                    <div className="flex items-center gap-2 p-3 rounded-xl border border-emerald-100 dark:border-emerald-900/20 bg-emerald-50/50 dark:bg-emerald-950/10">
                      <CheckCircle className="w-4 h-4 text-emerald-500" />
                      <span className="text-xs font-medium text-emerald-800 dark:text-emerald-300">
                        Nenhuma divergência encontrada nos limites do perfil padrão.
                      </span>
                    </div>
                  )}
                  {diferencas.length > 0 && (
                    <p className={`text-xs ${MUTED}`}>
                      {diferencas.length} {diferencas.length === 1 ? 'valor divergiu' : 'valores divergiram'} da leitura do
                      Gemini; vale o cálculo do código.
                    </p>
                  )}
                </div>

                {/* Ponto britânico */}
                {britanico?.conclusivo && britanico.sinal_risco ? (
                  <div className="p-3 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-xs text-amber-800 dark:text-amber-300 space-y-1">
                    <div className="font-bold">Sinal de risco: ponto britânico</div>
                    <p>
                      {britanico.fracao_uniforme != null
                        ? `${Math.round(britanico.fracao_uniforme * 100)}% dos dias têm horários praticamente idênticos. `
                        : 'Horários praticamente idênticos ao longo do período. '}
                      É um indício para conferir, não é prova de fraude.
                    </p>
                  </div>
                ) : britanico && !britanico.conclusivo ? (
                  <p className={`text-xs ${MUTED}`}>Ponto britânico: sem dias suficientes para concluir.</p>
                ) : null}

                {analise.analise && (
                  <div className="space-y-3">
                    <h4 className={TITULO_SECAO}>Parecer da auditoria (IA)</h4>
                    <div className="p-4 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#150c18] text-sm text-[#2d0a33] dark:text-[#f8f5fc] leading-relaxed italic">
                      “{analise.analise}”
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          <PaginaImagem documentoId={documentoId} />
        </div>

        <div className="p-4 border-t border-[#ebe5ef] dark:border-[#2f1e39] bg-[#fbf9fc] dark:bg-[#1f1325] flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2 rounded-xl bg-[#3e0b48] dark:bg-[#9917a2] text-white text-sm font-bold shadow-sm hover:opacity-90 transition-opacity cursor-pointer"
          >
            Fechar
          </button>
        </div>
      </div>
    </div>
  )
}

export default AuditoriaPontoModal
