import React from 'react'
import { Plus } from 'lucide-react'
import type { PerfilJornadaDetalhe, PerfilJornadaResumo } from '../services/api'
import { BTN, BTN_SEC, CARD, Selo } from './formUi'
import { VigenciaSelo } from './ConvencaoDetalhe'
import { contarDiferencas, descreverVigencia, hojeIso } from '../utils/convencoes'

const SUAVE = 'text-[#6e6378] dark:text-[#a093a8]'

const plural = (n: number, um: string, varios: string) => `${n} ${n === 1 ? um : varios}`

const textoContratos = (n: number, solo: boolean): string =>
  solo
    ? n === 0
      ? 'não está em uso'
      : 'em uso na sua empresa'
    : n === 0
      ? 'sem contratos'
      : `usada em ${plural(n, 'contrato', 'contratos')}`

interface Props {
  perfis: PerfilJornadaResumo[]
  /** Detalhes já carregados (para contar as regras diferentes do Padrão). */
  detalhes: Record<string, PerfilJornadaDetalhe>
  /** Escopo de cada convenção (só a plataforma o vê). */
  escopoDe?: (p: PerfilJornadaResumo) => string | undefined
  /** Convite do estado vazio: só aparece para quem pode cadastrar. */
  onNova?: () => void
  onVer: (perfil: string) => void
  /** Empresa solo: os textos não falam em contrato nem lote. */
  solo?: boolean
}

export const ConvencoesLista: React.FC<Props> = ({ perfis, detalhes, escopoDe, onNova, onVer, solo = false }) => {
  const padrao = perfis.find((p) => p.padrao)
  const hoje = hojeIso()
  const demais = perfis
    .filter((p) => !p.padrao)
    .sort((a, b) => {
      const va = descreverVigencia(a.vigencia_inicio, a.vigencia_fim, hoje).estado === 'vencida' ? 1 : 0
      const vb = descreverVigencia(b.vigencia_inicio, b.vigencia_fim, hoje).estado === 'vencida' ? 1 : 0
      return va - vb || a.nome.localeCompare(b.nome, 'pt-BR')
    })
  const padraoDet = detalhes[padrao?.perfil ?? '']

  const diferentes = (p: PerfilJornadaResumo): string => {
    const det = detalhes[p.perfil]
    if (!det || !padraoDet) return plural(p.parametros_proprios, 'regra própria', 'regras próprias')
    const n = contarDiferencas(det.efetivo, padraoDet.efetivo)
    return n === 0 ? 'Nenhuma regra diferente do Padrão' : `${plural(n, 'regra diferente', 'regras diferentes')} do Padrão`
  }

  return (
    <div className="space-y-5">
      {padrao && (
        <div className={`${CARD} p-4 flex flex-wrap items-center justify-between gap-3`}>
          <div className="min-w-0">
            <h2 className="text-base font-bold text-[#2d0a33] dark:text-white">Padrão</h2>
            <p className={`text-xs mt-0.5 ${SUAVE}`}>
              CLT e Portaria MTP 671/2021 · referência, não editável
              {solo ? (padrao.contratos > 0 ? ' · em uso na sua empresa' : '') : ` · ${plural(padrao.contratos, 'contrato', 'contratos')}`}
            </p>
          </div>
          <button type="button" onClick={() => onVer(padrao.perfil)} className={BTN_SEC}>
            Ver
          </button>
        </div>
      )}

      {demais.length === 0 ? (
        <div className={`${CARD} p-8 text-center`}>
          <h2 className="text-base font-bold text-[#2d0a33] dark:text-white">Nenhuma convenção cadastrada</h2>
          <p className={`text-sm mt-1 max-w-md mx-auto ${SUAVE}`}>
            {onNova
              ? 'Cadastre a convenção da categoria para que a análise use os limites dela.'
              : 'Enquanto não houver uma convenção, a análise usa o Padrão.'}
          </p>
          {onNova && (
            <button type="button" onClick={onNova} className={`${BTN} mx-auto mt-4`}>
              <Plus className="w-4 h-4" aria-hidden="true" />
              Nova convenção
            </button>
          )}
        </div>
      ) : (
        <ul className={`${CARD} divide-y divide-[#ebe5ef] dark:divide-[#2f1e39] list-none m-0 p-0`}>
          {demais.map((p) => {
            const escopo = escopoDe?.(p)
            return (
              <li key={p.perfil} className="p-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">{p.nome}</h3>
                    {escopo && <Selo tom="cinza">{escopo}</Selo>}
                  </div>
                  {p.sindicato && <p className={`text-xs ${SUAVE}`}>{p.sindicato}</p>}
                  <p className={`text-xs tabular-nums ${SUAVE}`}>
                    {diferentes(p)} · {textoContratos(p.contratos, solo)}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <VigenciaSelo inicio={p.vigencia_inicio} fim={p.vigencia_fim} />
                  <button
                    type="button"
                    onClick={() => onVer(p.perfil)}
                    aria-label={`Ver ${p.nome}`}
                    className={BTN_SEC}
                  >
                    Ver
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
