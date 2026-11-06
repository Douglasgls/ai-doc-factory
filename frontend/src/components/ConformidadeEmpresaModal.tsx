import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, CheckCircle, Clock, Info, X } from 'lucide-react'
import { apiService } from '../services/api'
import { formatarData } from './auditoriaPonto'
import {
  FAIXAS_CONFORMIDADE,
  ORDEM_CRITERIOS,
  agruparAcoes,
  corDaFaixa,
  explicarCriterio,
  explicarDesconto,
  formatarPontos,
  gerarResumo,
  motivosProvisorio,
  rotuloTipoDoc,
  somaDescontos,
  type Avaliacao,
  type Classificacao,
  type ConformidadeEmpresa,
  type CorFaixa,
  type InfoDocumento,
  type Rotulos,
} from './conformidadeEmpresa'

interface Props {
  cnpj: string
  razaoSocial: string
  onClose: () => void
}

const COR_FUNDO: Record<CorFaixa, string> = { verde: 'bg-emerald-500', ambar: 'bg-amber-500', vermelho: 'bg-red-500' }
const COR_TEXTO: Record<CorFaixa, string> = {
  verde: 'text-emerald-700 dark:text-emerald-400',
  ambar: 'text-amber-700 dark:text-amber-400',
  vermelho: 'text-red-700 dark:text-red-400',
}
const COR_BADGE: Record<CorFaixa, string> = {
  verde: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  ambar: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
  vermelho: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
}

const TITULO_SECAO = 'text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider'
const MUTED = 'text-[#6e6378] dark:text-[#a093a8]'
const TEXTO = 'text-[#2d0a33] dark:text-[#f8f5fc]'
const CARTAO = 'p-4 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#150c18]'
/** Listas longas começam recolhidas. */
const LIMITE_RECOLHER = 5

const Badge: React.FC<{ classificacao: Classificacao | null }> = ({ classificacao }) => (
  <span
    className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
      classificacao ? COR_BADGE[corDaFaixa(classificacao)] : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    }`}
  >
    {classificacao ?? 'Sem nota'}
  </span>
)

const Secao: React.FC<{ titulo: string; children: React.ReactNode }> = ({ titulo, children }) => (
  <section className="space-y-3">
    <h4 className={TITULO_SECAO}>{titulo}</h4>
    {children}
  </section>
)

const ConformidadeEmpresaModal: React.FC<Props> = ({ cnpj, razaoSocial, onClose }) => {
  const [dados, setDados] = useState<ConformidadeEmpresa | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [rotulos, setRotulos] = useState<Rotulos>({})
  const [documentos, setDocumentos] = useState<Map<number, InfoDocumento>>(new Map())
  const [recarga, setRecarga] = useState(0)

  const carregar = useCallback(() => {
    setDados(null)
    setErro(null)
    setRecarga((n) => n + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    apiService
      .getEmpresaConformidade(cnpj)
      .then((r) => {
        if (ativo) setDados(r as unknown as ConformidadeEmpresa)
      })
      .catch((e: unknown) => {
        if (ativo) setErro(e instanceof Error ? e.message : 'Não foi possível carregar a conformidade.')
      })
    return () => {
      ativo = false
    }
  }, [cnpj, recarga])

  // Nomes dos tipos e dos documentos: melhor esforço, a tela funciona sem eles (cai no código do tipo).
  useEffect(() => {
    let ativo = true
    apiService
      .getTipos()
      .then((ts) => {
        if (ativo) setRotulos(Object.fromEntries(ts.map((t) => [t.slug, t.nome])))
      })
      .catch(() => undefined)
    apiService
      .getDocumentosAgrupados()
      .then((r) => {
        if (!ativo) return
        const mapa = new Map<number, InfoDocumento>()
        for (const g of r.grupos) {
          for (const d of g.documentos) mapa.set(d.id, { tipo: d.tipo, nome_arquivo: d.nome_arquivo, lote_id: d.lote_id })
        }
        setDocumentos(mapa)
      })
      .catch(() => undefined)
    return () => {
      ativo = false
    }
  }, [])

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [onClose])

  const g = dados?.geral
  const faixa = corDaFaixa(g?.classificacao)
  const resumo = useMemo(() => (dados ? gerarResumo(dados, rotulos) : ''), [dados, rotulos])
  const motivos = useMemo(() => (g ? motivosProvisorio(g, rotulos) : []), [g, rotulos])
  const acoes = useMemo(() => (g ? agruparAcoes(g, rotulos) : []), [g, rotulos])
  const totalDescontado = g ? somaDescontos(g) : 0

  /** Rótulo de um documento da lista por documento: o tipo vem de /documentos, ou dos descontos/pendências. */
  const tipoDoDocumento = (id: number, a: Avaliacao): string | null =>
    documentos.get(id)?.tipo ??
    a.descontos.find((d) => d.tipo)?.tipo ??
    a.pendencias.find((p) => p.tipo)?.tipo ??
    null

  const porDocumento = dados ? Object.entries(dados.por_documento) : []
  const porTipo = dados ? Object.entries(dados.por_tipo) : []

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Conformidade de ${razaoSocial}`}
        className="w-full max-w-3xl bg-white dark:bg-[#1a1120] rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] shadow-2xl overflow-hidden max-h-[90vh] flex flex-col"
      >
        <div className="p-6 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between bg-[#fbf9fc] dark:bg-[#1f1325]">
          <div className="min-w-0">
            <h3 className={`text-lg font-bold ${TEXTO}`}>Como a nota foi calculada</h3>
            <p className={`text-xs truncate ${MUTED}`}>
              {razaoSocial} · <span className="font-mono">{cnpj}</span>
            </p>
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

        <div className="p-6 overflow-y-auto space-y-6">
          {!dados && !erro && (
            <div className={`flex items-center gap-2 text-sm ${MUTED}`}>
              <Clock className="w-4 h-4 text-[#9333ea] animate-spin" /> Carregando a conformidade...
            </div>
          )}
          {erro && (
            <div className="p-4 rounded-xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-sm text-red-700 dark:text-red-400 space-y-2">
              <p>{erro}</p>
              <button
                type="button"
                onClick={carregar}
                className="px-3 py-1 rounded-lg text-xs font-bold bg-red-500 text-white cursor-pointer"
              >
                Tentar de novo
              </button>
            </div>
          )}

          {dados && g && (
            <>
              {/* 1. Resumo */}
              <div className="p-4 rounded-2xl border border-[#ece4f1] dark:border-[#382240] bg-[#f8f5fa] dark:bg-[#201326]">
                <p className={`text-sm font-semibold leading-relaxed ${TEXTO}`}>{resumo}</p>
              </div>

              {/* 2. Score e faixa */}
              <Secao titulo="Nota e faixa">
                <div className="flex flex-wrap items-center gap-4">
                  <div
                    className={`w-16 h-16 rounded-full flex items-center justify-center text-white font-bold shrink-0 ${
                      g.score != null ? COR_FUNDO[faixa] : 'bg-slate-400 dark:bg-slate-600'
                    } ${g.score != null ? 'text-xl' : 'text-[10px] text-center leading-tight px-1'}`}
                  >
                    {g.score != null ? g.score : 'Sem nota'}
                  </div>
                  <div>
                    <div className={`text-sm font-bold ${g.score != null ? COR_TEXTO[faixa] : MUTED}`}>
                      {g.classificacao ?? 'Sem nota'}
                    </div>
                    <div className={`text-[11px] ${MUTED}`}>De 0 a 100. Quanto maior, melhor.</div>
                  </div>
                  <ul className="ml-auto flex flex-wrap gap-2" aria-label="Faixas de classificação">
                    {FAIXAS_CONFORMIDADE.map((f) => (
                      <li
                        key={f.nome}
                        className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold ${COR_BADGE[corDaFaixa(f.nome)]} ${
                          f.nome === g.classificacao ? 'ring-2 ring-offset-1 ring-[#9333ea] dark:ring-offset-[#1a1120]' : ''
                        }`}
                      >
                        {f.minimo}–{f.maximo} {f.nome}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className={`flex items-start gap-2 text-xs ${MUTED}`}>
                  <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
                  <span>
                    Mede a documentação da empresa; o risco da folha de ponto é outra análise e não entra nesta nota.
                  </span>
                </div>
              </Secao>

              {/* 3. Provisório */}
              {g.provisorio && (
                <div className="p-4 rounded-xl border border-amber-200 dark:border-amber-900/40 bg-amber-50 dark:bg-amber-950/20 text-amber-800 dark:text-amber-300 space-y-2">
                  <div className="flex items-center gap-2 text-sm font-bold">
                    <AlertTriangle className="w-4 h-4 shrink-0" /> Esta nota ainda pode mudar
                  </div>
                  {motivos.length > 0 ? (
                    <ul className="text-xs leading-relaxed list-disc pl-5 space-y-1">
                      {motivos.map((m) => (
                        <li key={m}>{m}</li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-xs">Há itens ainda sem análise completa.</p>
                  )}
                </div>
              )}

              {/* 4. Critérios */}
              <Secao titulo="Os três critérios">
                <div className="grid gap-3 sm:grid-cols-3">
                  {ORDEM_CRITERIOS.map((chave) => {
                    const c = explicarCriterio(chave, g.criterios[chave])
                    return (
                      <div key={chave} className={`${CARTAO} space-y-2`}>
                        <div className={`text-sm font-bold ${TEXTO}`}>{c.rotulo}</div>
                        <p className={`text-[11px] leading-snug ${MUTED}`}>{c.mede}</p>
                        {c.situacao === 'calculado' ? (
                          <>
                            <div className={`text-2xl font-extrabold ${TEXTO}`}>{c.nota}</div>
                            <div className={`text-xs ${TEXTO}`}>{c.contagem}</div>
                          </>
                        ) : (
                          <div className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                            {c.situacao === 'pendente' ? 'Ainda sem dados para avaliar' : 'Não se aplica'}
                          </div>
                        )}
                        <div className={`text-[11px] ${MUTED}`}>
                          Peso {c.peso}
                          {c.pesoEfetivo && <> · nesta nota vale {c.pesoEfetivo}</>}
                        </div>
                        {c.aviso && <p className={`text-[11px] leading-snug ${MUTED}`}>{c.aviso}</p>}
                      </div>
                    )
                  })}
                </div>
              </Secao>

              {/* 5. O que derruba a nota */}
              <Secao titulo="O que está derrubando a nota">
                {g.descontos.length === 0 ? (
                  <div className="flex items-center gap-2 p-3 rounded-xl border border-emerald-100 dark:border-emerald-900/20 bg-emerald-50/50 dark:bg-emerald-950/10">
                    <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                    <span className="text-xs font-medium text-emerald-800 dark:text-emerald-300">
                      Nenhum desconto: os documentos analisados não têm problemas.
                    </span>
                  </div>
                ) : (
                  <>
                    <ul className="space-y-2">
                      {g.descontos.map((d, i) => {
                        const e = explicarDesconto(d, rotulos)
                        const info = e.documento != null ? documentos.get(e.documento) : undefined
                        return (
                          <li
                            key={`${d.regra}-${d.documento}-${d.campo}-${i}`}
                            className="flex items-start gap-3 p-3 rounded-xl border border-red-100 dark:border-red-900/30 bg-red-50/50 dark:bg-red-950/10"
                          >
                            <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                            <div className="min-w-0 flex-1 space-y-1">
                              <div className="text-sm font-bold text-red-800 dark:text-red-300">{e.titulo}</div>
                              {e.detalhe && <div className="text-xs text-red-700 dark:text-red-400">{e.detalhe}</div>}
                              {e.valores.length > 0 && (
                                <ul className="text-xs text-red-700 dark:text-red-400 list-disc pl-4">
                                  {e.valores.map((v) => (
                                    <li key={v.rotulo}>
                                      {v.rotulo}: <strong>{v.valor}</strong>
                                    </li>
                                  ))}
                                </ul>
                              )}
                              <div className={`text-[11px] ${MUTED}`}>
                                Critério: {explicarCriterio(d.criterio, g.criterios[d.criterio]).rotulo}
                                {e.documento != null && (
                                  <>
                                    {' '}
                                    · documento {e.documento}
                                    {info?.nome_arquivo && <> ({info.nome_arquivo})</>}
                                  </>
                                )}
                              </div>
                            </div>
                            <div className="text-sm font-bold text-red-700 dark:text-red-400 shrink-0">
                              −{formatarPontos(e.pontos)} {e.pontos === 1 ? 'ponto' : 'pontos'}
                            </div>
                          </li>
                        )
                      })}
                    </ul>
                    <p className={`text-[11px] ${MUTED}`}>
                      Total descontado: {formatarPontos(totalDescontado)} pontos. A nota é 100 menos os descontos,
                      arredondada.
                    </p>
                  </>
                )}
              </Secao>

              {/* 6. O que fazer */}
              <Secao titulo="O que fazer">
                {acoes.length === 0 ? (
                  <p className={`text-xs ${MUTED}`}>Nada a fazer por enquanto.</p>
                ) : (
                  <ul className="space-y-2">
                    {acoes.map((a) => (
                      <li key={a.chave} className={CARTAO}>
                        <div className={`text-sm font-bold ${TEXTO}`}>{a.titulo}</div>
                        <p className={`text-xs mt-0.5 ${MUTED}`}>{a.texto}</p>
                        <p className={`text-[11px] mt-1 ${MUTED}`}>Afeta: {a.itens.join('; ')}</p>
                      </li>
                    ))}
                  </ul>
                )}
                <p className={`text-xs ${MUTED}`}>
                  A nota é recalculada sozinha quando a documentação muda (novo lote ou revisão). Não há nada a ajustar na
                  nota em si.
                </p>
              </Secao>

              {/* 7. Por tipo e por documento */}
              <Secao titulo="Por tipo e por documento">
                <p className={`text-xs ${MUTED}`}>
                  Por tipo mostra se cada tipo de documento foi enviado e como está. Por documento mostra cada arquivo
                  separadamente. As duas visões usam a mesma conta, com os pesos redistribuídos entre os critérios que se
                  aplicam.
                </p>
                <p className={`text-xs ${MUTED}`}>Validade conferida em {formatarData(dados.data_referencia)}.</p>

                <details open={porTipo.length <= LIMITE_RECOLHER + 2} className="group rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39]">
                  <summary className={`cursor-pointer list-none px-4 py-2 text-sm font-bold ${TEXTO}`}>
                    Por tipo ({porTipo.length})
                  </summary>
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className={`${MUTED} border-t border-[#ebe5ef] dark:border-[#2f1e39]`}>
                        <th className="px-4 py-2 font-semibold">Tipo</th>
                        <th className="px-2 py-2 font-semibold">Enviado</th>
                        <th className="px-2 py-2 font-semibold text-right">Nota</th>
                        <th className="px-4 py-2 font-semibold text-right">Faixa</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                      {porTipo.map(([tipo, a]) => {
                        const comp = a.criterios.completude
                        const qtd = dados.documentos_por_tipo[tipo] ?? 0
                        const presenca = comp.aplicavel
                          ? comp.pendente
                            ? 'Em verificação'
                            : comp.nota === 1
                              ? `Sim (${qtd})`
                              : 'Não'
                          : qtd > 0
                            ? `${qtd} ${qtd === 1 ? 'documento' : 'documentos'}`
                            : '—'
                        return (
                          <tr key={tipo} className={TEXTO}>
                            <td className="px-4 py-2">
                              {rotuloTipoDoc(tipo, rotulos)}
                              {comp.aplicavel && <span className={`ml-1 ${MUTED}`}>(obrigatório)</span>}
                            </td>
                            <td className="px-2 py-2">{presenca}</td>
                            <td className="px-2 py-2 text-right font-semibold">{a.score ?? '—'}</td>
                            <td className="px-4 py-2 text-right">
                              <Badge classificacao={a.classificacao} />
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </details>

                <details open={porDocumento.length <= LIMITE_RECOLHER} className="group rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39]">
                  <summary className={`cursor-pointer list-none px-4 py-2 text-sm font-bold ${TEXTO}`}>
                    Por documento ({porDocumento.length})
                  </summary>
                  {porDocumento.length === 0 ? (
                    <p className={`px-4 pb-3 text-xs ${MUTED}`}>Nenhum documento analisado.</p>
                  ) : (
                    <ul className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39] border-t border-[#ebe5ef] dark:border-[#2f1e39]">
                      {porDocumento.map(([id, a]) => {
                        const n = Number(id)
                        const tipo = tipoDoDocumento(n, a)
                        const nome = documentos.get(n)?.nome_arquivo
                        const problemas = a.descontos.length
                        return (
                          <li key={id} className={`flex items-center gap-3 px-4 py-2 text-xs ${TEXTO}`}>
                            <div className="min-w-0 flex-1">
                              <div className="font-semibold truncate">
                                {tipo ? rotuloTipoDoc(tipo, rotulos) : 'Documento'} · nº {id}
                              </div>
                              <div className={`${MUTED} truncate`}>
                                {nome && <>{nome} · </>}
                                {problemas > 0
                                  ? `${problemas} ${problemas === 1 ? 'problema' : 'problemas'}`
                                  : a.pendencias.length > 0
                                    ? `${a.pendencias.length} ${a.pendencias.length === 1 ? 'pendência' : 'pendências'}`
                                    : 'sem problemas'}
                              </div>
                            </div>
                            <span className="font-semibold">{a.score ?? '—'}</span>
                            <Badge classificacao={a.classificacao} />
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </details>
              </Secao>

              {/* 8. Ressalva */}
              <div className={`flex items-start gap-2 text-[11px] ${MUTED}`}>
                <Info className="w-3.5 h-3.5 shrink-0 mt-px" />
                <span>
                  A Completude verifica se a empresa tem ao menos um documento de cada tipo obrigatório, não se cada
                  funcionário tem o seu. É um apoio à conferência, não um parecer jurídico.
                </span>
              </div>
            </>
          )}
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

export default ConformidadeEmpresaModal
