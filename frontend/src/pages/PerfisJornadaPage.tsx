import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { AlertTriangle, ChevronRight, Clock, FileText, Loader2, Pencil, Plus } from 'lucide-react'
import {
  apiService,
  type Contrato,
  type PerfilJornadaDetalhe,
  type PerfilJornadaResumo,
} from '../services/api'
import { BTN, BTN_SEC, CARD, ErroBox, Selo, TD, TH } from '../components/formUi'
import { PerfilJornadaForm } from '../components/PerfilJornadaForm'
import { PERFIL_PADRAO, formatarData, formatarValor, rotuloParametro } from '../utils/perfisJornada'

type Tela = { tipo: 'lista' } | { tipo: 'ver'; perfil: string } | { tipo: 'form'; perfil: string | null }

interface Props {
  onBack: () => void
}

const PerfisJornadaPage: React.FC<Props> = ({ onBack }) => {
  const [tela, setTela] = useState<Tela>({ tipo: 'lista' })
  const [perfis, setPerfis] = useState<PerfilJornadaResumo[]>([])
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [padrao, setPadrao] = useState<PerfilJornadaDetalhe | null>(null)
  const [detalhe, setDetalhe] = useState<PerfilJornadaDetalhe | null>(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState<string | null>(null)

  const catalogo = useMemo(
    () => (padrao ? padrao.proprios.filter((p) => p.vigente_desde === null) : []),
    [padrao],
  )

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      const [ps, cs, pad] = await Promise.all([
        apiService.getPerfisJornada(),
        apiService.getContratos(),
        apiService.getPerfilJornada(PERFIL_PADRAO),
      ])
      setPerfis(ps)
      setContratos(cs)
      setPadrao(pad)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao carregar os perfis de jornada')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void carregar()
  }, [carregar])

  const perfilAlvo = tela.tipo === 'lista' ? null : tela.perfil
  useEffect(() => {
    if (!perfilAlvo) return
    let ativo = true
    apiService
      .getPerfilJornada(perfilAlvo)
      .then((d) => {
        if (ativo) {
          setDetalhe(d)
          setErro(null)
        }
      })
      .catch((e) => {
        if (ativo) setErro(e instanceof Error ? e.message : 'Erro ao carregar o perfil')
      })
    return () => {
      ativo = false
      setDetalhe(null)
    }
  }, [perfilAlvo])

  const trocarContrato = async (contratoId: number, perfil: string) => {
    const c = await apiService.associarPerfilJornada(contratoId, perfil)
    setContratos((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x)))
    setPerfis(await apiService.getPerfisJornada())
  }

  const voltarLista = () => {
    setTela({ tipo: 'lista' })
    void carregar()
  }

  const titulo =
    tela.tipo === 'lista' ? null : tela.tipo === 'form' ? (tela.perfil ? `Editar ${tela.perfil}` : 'Novo perfil') : tela.perfil

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-xs sm:text-sm text-[#877991] dark:text-[#95849f]">
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer inline-flex items-center gap-1.5"
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Documentos</span>
        </button>
        <ChevronRight className="w-3.5 h-3.5 opacity-60" />
        {titulo ? (
          <>
            <button onClick={voltarLista} className="hover:text-[#2d0a33] dark:hover:text-white cursor-pointer">
              Perfis de jornada
            </button>
            <ChevronRight className="w-3.5 h-3.5 opacity-60" />
            <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">{titulo}</span>
          </>
        ) : (
          <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Perfis de jornada</span>
        )}
      </nav>

      <div className="flex items-start sm:items-center gap-3.5">
        <div className="w-11 h-11 rounded-2xl bg-purple-950/40 border border-purple-800/40 flex items-center justify-center text-purple-400 shrink-0 shadow-sm">
          <Clock className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-[#2d0a33] dark:text-white tracking-tight">
            Perfis de jornada
          </h1>
          <p className="text-xs sm:text-sm text-[#877991] dark:text-[#a093a8] mt-0.5">
            Parâmetros da análise de folha de ponto (CLT e Portaria MTP 671/2021) e o perfil de cada contrato.
          </p>
        </div>
      </div>

      <ErroBox message={erro} />

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-6 h-6 animate-spin text-[#9333ea]" />
        </div>
      ) : tela.tipo === 'lista' ? (
        <>
          <ListaPerfis
            perfis={perfis}
            onVer={(perfil) => setTela({ tipo: 'ver', perfil })}
            onNovo={() => setTela({ tipo: 'form', perfil: null })}
          />
          <ContratosPerfis contratos={contratos} perfis={perfis} onTrocar={trocarContrato} />
        </>
      ) : tela.tipo === 'ver' ? (
        detalhe && (
          <VerPerfil
            detalhe={detalhe}
            catalogo={catalogo}
            onEditar={() => setTela({ tipo: 'form', perfil: detalhe.perfil })}
          />
        )
      ) : tela.perfil === null ? (
        <PerfilJornadaForm
          existente={null}
          catalogo={catalogo}
          onCancelar={voltarLista}
          onSalvo={(perfil) => {
            void carregar()
            setTela({ tipo: 'ver', perfil })
          }}
        />
      ) : (
        detalhe && (
          <PerfilJornadaForm
            existente={detalhe}
            catalogo={catalogo}
            onCancelar={() => setTela({ tipo: 'ver', perfil: detalhe.perfil })}
            onSalvo={(perfil) => {
              void carregar()
              setTela({ tipo: 'ver', perfil })
            }}
          />
        )
      )}
    </div>
  )
}

const ListaPerfis: React.FC<{
  perfis: PerfilJornadaResumo[]
  onVer: (perfil: string) => void
  onNovo: () => void
}> = ({ perfis, onVer, onNovo }) => (
  <div className={`${CARD} overflow-hidden`}>
    <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-3">
      <div>
        <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Perfis cadastrados</h3>
        <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
          {perfis.length} {perfis.length === 1 ? 'perfil' : 'perfis'}
        </p>
      </div>
      <button type="button" onClick={onNovo} className={BTN}>
        <Plus className="w-4 h-4" />
        Novo perfil
      </button>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse min-w-[560px]">
        <thead>
          <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
            <th className={TH}>Perfil</th>
            <th className={TH}>Tipo</th>
            <th className={TH}>Parâmetros próprios</th>
            <th className={TH}>Contratos</th>
            <th className={TH}></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
          {perfis.map((p) => (
            <tr key={p.perfil} className="hover:bg-slate-50/50 dark:hover:bg-[#23152c]/50 transition-colors">
              <td className={`${TD} font-bold font-mono`}>{p.perfil}</td>
              <td className={TD}>{p.padrao ? <Selo tom="ambar">Padrão (referência)</Selo> : <Selo tom="cinza">Próprio</Selo>}</td>
              <td className={TD}>{p.parametros_proprios}</td>
              <td className={TD}>{p.contratos}</td>
              <td className={TD}>
                <button type="button" onClick={() => onVer(p.perfil)} className={BTN_SEC}>
                  Ver
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
)

const VerPerfil: React.FC<{
  detalhe: PerfilJornadaDetalhe
  catalogo: { parametro: string; unidade: string }[]
  onEditar: () => void
}> = ({ detalhe, catalogo, onEditar }) => {
  const proprios = new Set(detalhe.proprios.map((p) => p.parametro))
  const unidades = new Map(catalogo.map((c) => [c.parametro, c.unidade]))
  const nomes = catalogo.map((c) => c.parametro)
  // parâmetro fora do catálogo (não deveria ocorrer): ainda aparece, na ordem alfabética
  for (const k of Object.keys(detalhe.efetivo).sort()) if (!unidades.has(k)) nomes.push(k)

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white font-mono">{detalhe.perfil}</h3>
          <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
            {detalhe.padrao
              ? 'Referência legal, somente leitura (muda só por migração).'
              : `${proprios.size} ${proprios.size === 1 ? 'parâmetro próprio' : 'parâmetros próprios'}; o restante é herdado do ${PERFIL_PADRAO}.`}
          </p>
        </div>
        {!detalhe.padrao && (
          <button type="button" onClick={onEditar} className={BTN_SEC}>
            <Pencil className="w-3.5 h-3.5" />
            Editar
          </button>
        )}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[760px]">
          <thead>
            <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
              <th className={TH}>Parâmetro</th>
              <th className={TH}>Valor</th>
              <th className={TH}>Vigência</th>
              <th className={TH}>Base legal</th>
              {!detalhe.padrao && <th className={TH}>Origem</th>}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
            {nomes.map((nome) => {
              const ef = detalhe.efetivo[nome]
              if (!ef) return null
              const un = unidades.get(nome) ?? 'min'
              const linhas = [
                { desde: null as string | null, valor: ef.valor, base: ef.base_legal },
                ...(ef.vigencias ?? []).map((v) => ({ desde: v.desde, valor: v.valor, base: v.base_legal })),
              ]
              return linhas.map((l, i) => (
                <tr key={`${nome}-${i}`} className="hover:bg-slate-50/50 dark:hover:bg-[#23152c]/50 transition-colors">
                  <td className={`${TD} font-semibold`}>{i === 0 ? rotuloParametro(nome) : ''}</td>
                  <td className={TD}>{formatarValor(nome, l.valor, un)}</td>
                  <td className={TD}>{l.desde ? `a partir de ${formatarData(l.desde)}` : 'base'}</td>
                  <td className={TD}>{l.base}</td>
                  {!detalhe.padrao && (
                    <td className={TD}>
                      {i === 0 &&
                        (proprios.has(nome) ? <Selo tom="verde">próprio</Selo> : <Selo tom="cinza">herdado do {PERFIL_PADRAO}</Selo>)}
                    </td>
                  )}
                </tr>
              ))
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const ContratosPerfis: React.FC<{
  contratos: Contrato[]
  perfis: PerfilJornadaResumo[]
  onTrocar: (contratoId: number, perfil: string) => Promise<void>
}> = ({ contratos, perfis, onTrocar }) => {
  const [pendente, setPendente] = useState<{ id: number; perfil: string } | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)

  const confirmar = async () => {
    if (!pendente) return
    setSalvando(true)
    setErro(null)
    try {
      await onTrocar(pendente.id, pendente.perfil)
      setPendente(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao trocar o perfil do contrato')
    } finally {
      setSalvando(false)
    }
  }

  return (
    <div className={`${CARD} overflow-hidden`}>
      <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39]">
        <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Perfil de cada contrato</h3>
        <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
          A troca vale para as análises feitas a partir daí. Lote sem contrato usa o {PERFIL_PADRAO}.
        </p>
      </div>
      <div className="px-5 pt-4">
        <ErroBox message={erro} />
      </div>
      {contratos.length === 0 ? (
        <p className="p-5 text-xs text-[#877991] dark:text-[#a093a8]">Nenhum contrato cadastrado.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[640px]">
            <thead>
              <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                <th className={TH}>Tomador</th>
                <th className={TH}>Prestador</th>
                <th className={TH}>Perfil de jornada</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
              {contratos.map((c) => {
                const emTroca = pendente?.id === c.id && pendente.perfil !== c.perfil_jornada
                return (
                  <React.Fragment key={c.id}>
                    <tr>
                      <td className={`${TD} font-bold`}>{c.tomador_nome}</td>
                      <td className={TD}>{c.prestador_razao_social}</td>
                      <td className={TD}>
                        <select
                          aria-label={`Perfil de jornada do contrato ${c.id}`}
                          className="px-3 py-1.5 rounded-xl text-sm font-mono bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white"
                          value={pendente?.id === c.id ? pendente.perfil : c.perfil_jornada}
                          disabled={salvando}
                          onChange={(e) => {
                            setErro(null)
                            setPendente(e.target.value === c.perfil_jornada ? null : { id: c.id, perfil: e.target.value })
                          }}
                        >
                          {perfis.map((p) => (
                            <option key={p.perfil} value={p.perfil}>{p.perfil}</option>
                          ))}
                          {!perfis.some((p) => p.perfil === c.perfil_jornada) && (
                            <option value={c.perfil_jornada}>{c.perfil_jornada}</option>
                          )}
                        </select>
                      </td>
                    </tr>
                    {emTroca && pendente && (
                      <tr>
                        <td colSpan={3} className="px-5 pb-4">
                          <div
                            role="alert"
                            className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-300 text-xs space-y-2"
                          >
                            <div className="flex items-start gap-2">
                              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                              <span>
                                Trocar de <b>{c.perfil_jornada}</b> para <b>{pendente.perfil}</b> vale para as próximas
                                análises. As análises de ponto já feitas não são refeitas automaticamente: é preciso
                                reprocessar cada documento.
                              </span>
                            </div>
                            <div className="flex gap-2">
                              <button type="button" onClick={confirmar} disabled={salvando} className={BTN_SEC}>
                                {salvando && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                                Confirmar troca
                              </button>
                              <button type="button" onClick={() => setPendente(null)} disabled={salvando} className={BTN_SEC}>
                                Cancelar
                              </button>
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default PerfisJornadaPage
