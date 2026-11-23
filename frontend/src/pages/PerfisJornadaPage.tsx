import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { ChevronRight, Clock, FileText, Loader2, Plus } from 'lucide-react'
import {
  apiService,
  type Contrato,
  type PerfilJornadaDetalhe,
  type PerfilJornadaResumo,
  type Prestador,
} from '../services/api'
import { BTN, ErroBox } from '../components/formUi'
import { ConvencaoContratos } from '../components/ConvencaoContratos'
import { ConvencaoDetalhe } from '../components/ConvencaoDetalhe'
import { ConvencoesLista } from '../components/ConvencoesLista'
import { PerfilJornadaForm } from '../components/PerfilJornadaForm'
import { rotuloEscopo } from '../utils/convencoes'
import { PERFIL_PADRAO } from '../utils/perfisJornada'

type Tela = { tipo: 'lista' } | { tipo: 'ver'; perfil: string } | { tipo: 'form'; perfil: string | null }

interface Props {
  onBack: () => void
  /** Admin de empresa própria: vê as convenções e escolhe a do próprio contrato; cadastra só as dele. */
  modoEscolha?: boolean
}

const SUAVE = 'text-[#877991] dark:text-[#a093a8]'

const PerfisJornadaPage: React.FC<Props> = ({ onBack, modoEscolha = false }) => {
  const [tela, setTela] = useState<Tela>({ tipo: 'lista' })
  const [perfis, setPerfis] = useState<PerfilJornadaResumo[]>([])
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [prestadores, setPrestadores] = useState<Prestador[]>([])
  const [detalhes, setDetalhes] = useState<Record<string, PerfilJornadaDetalhe>>({})
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState<string | null>(null)

  const padrao = detalhes[PERFIL_PADRAO] ?? null
  const catalogo = useMemo(() => (padrao ? padrao.proprios.filter((p) => p.vigente_desde === null) : []), [padrao])

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      const [ps, cs, pres] = await Promise.all([
        apiService.getPerfisJornada(),
        apiService.getContratos(),
        modoEscolha ? Promise.resolve([] as Prestador[]) : apiService.getPrestadores().catch(() => [] as Prestador[]),
      ])
      // o detalhe de cada convenção mostra quantas regras ela muda em relação ao Padrão
      const ds = await Promise.all([PERFIL_PADRAO, ...ps.filter((p) => !p.padrao).map((p) => p.perfil)].map((p) => apiService.getPerfilJornada(p)))
      setPerfis(ps)
      setContratos(cs)
      setPrestadores(pres)
      setDetalhes(Object.fromEntries(ds.map((d) => [d.perfil, d])))
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao carregar as convenções')
    } finally {
      setLoading(false)
    }
  }, [modoEscolha])

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void carregar()
  }, [carregar])

  const chaveTela = tela.tipo === 'lista' ? 'lista' : `${tela.tipo}:${tela.perfil}`
  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [chaveTela])

  const nomePrestador = useCallback(
    (id: number) => prestadores.find((p) => p.id === id)?.razao_social,
    [prestadores],
  )
  const escopoDe = modoEscolha ? undefined : (c: { geral: boolean; prestador_id: number | null }) => rotuloEscopo(c, nomePrestador)

  const trocarContrato = async (contratoId: number, perfil: string) => {
    const c = await apiService.associarPerfilJornada(contratoId, perfil)
    setContratos((cs) => cs.map((x) => (x.id === c.id ? { ...x, ...c } : x)))
    setPerfis(await apiService.getPerfisJornada())
  }

  const voltarLista = () => {
    setTela({ tipo: 'lista' })
    void carregar()
  }

  const alvo = tela.tipo === 'lista' ? null : tela.perfil
  const detalhe = alvo ? (detalhes[alvo] ?? null) : null
  const titulo =
    tela.tipo === 'lista'
      ? null
      : tela.tipo === 'form'
        ? tela.perfil
          ? `Editar ${detalhe?.nome ?? ''}`.trim()
          : 'Nova convenção'
        : detalhe?.padrao
          ? 'Padrão'
          : (detalhe?.nome ?? '')

  return (
    <div className="space-y-6">
      <nav aria-label="Você está em" className={`flex items-center gap-2 text-xs sm:text-sm ${SUAVE}`}>
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer inline-flex items-center gap-1.5"
        >
          <FileText className="w-3.5 h-3.5" aria-hidden="true" />
          <span>Documentos</span>
        </button>
        <ChevronRight className="w-3.5 h-3.5 opacity-60" aria-hidden="true" />
        {titulo ? (
          <>
            <button onClick={voltarLista} className="hover:text-[#2d0a33] dark:hover:text-white cursor-pointer">
              Convenções coletivas
            </button>
            <ChevronRight className="w-3.5 h-3.5 opacity-60" aria-hidden="true" />
            <span aria-current="page" className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
              {titulo}
            </span>
          </>
        ) : (
          <span aria-current="page" className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
            Convenções coletivas
          </span>
        )}
      </nav>

      {tela.tipo === 'lista' && (
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start sm:items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-[#f4e8f7] dark:bg-[#34163d] flex items-center justify-center text-[#5c1363] dark:text-[#f38df9] shrink-0">
              <Clock className="w-5 h-5" aria-hidden="true" />
            </div>
            <div>
              <h1 className="text-xl sm:text-2xl font-bold text-[#2d0a33] dark:text-white tracking-tight">
                Convenções coletivas
              </h1>
              <p className={`text-xs sm:text-sm mt-0.5 ${SUAVE}`}>
                Regras de jornada usadas na análise das folhas de ponto.
              </p>
            </div>
          </div>
          {!loading && (
            <button type="button" onClick={() => setTela({ tipo: 'form', perfil: null })} className={BTN}>
              <Plus className="w-4 h-4" aria-hidden="true" />
              Nova convenção
            </button>
          )}
        </div>
      )}

      <ErroBox message={erro} />

      {loading ? (
        <div className="flex justify-center py-16" role="status" aria-label="Carregando">
          <Loader2 className="w-6 h-6 animate-spin motion-reduce:animate-none text-[#9333ea]" />
        </div>
      ) : tela.tipo === 'lista' ? (
        <>
          <ConvencoesLista
            perfis={perfis}
            detalhes={detalhes}
            escopoDe={escopoDe}
            onNova={() => setTela({ tipo: 'form', perfil: null })}
            onVer={(perfil) => setTela({ tipo: 'ver', perfil })}
          />
          <ConvencaoContratos contratos={contratos} perfis={perfis} onTrocar={trocarContrato} modoEscolha={modoEscolha} />
        </>
      ) : tela.tipo === 'ver' ? (
        detalhe &&
        padrao && (
          <ConvencaoDetalhe
            detalhe={detalhe}
            padrao={padrao}
            escopo={escopoDe?.(detalhe)}
            onEditar={() => setTela({ tipo: 'form', perfil: detalhe.perfil })}
            onVoltar={voltarLista}
          />
        )
      ) : tela.perfil === null ? (
        <PerfilJornadaForm existente={null} catalogo={catalogo} onCancelar={voltarLista} onSalvo={voltarLista} />
      ) : (
        detalhe && (
          <PerfilJornadaForm
            existente={detalhe}
            catalogo={catalogo}
            onCancelar={() => setTela({ tipo: 'ver', perfil: detalhe.perfil })}
            onSalvo={voltarLista}
          />
        )
      )}
    </div>
  )
}

export default PerfisJornadaPage
