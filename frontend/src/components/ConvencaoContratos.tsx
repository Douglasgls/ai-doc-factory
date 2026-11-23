import React, { useState } from 'react'
import { AlertTriangle, Loader2 } from 'lucide-react'
import type { Contrato, PerfilJornadaResumo } from '../services/api'
import { BTN_SEC, CARD, ErroBox, TD, TH_PLANO } from './formUi'
import { descreverVigencia, hojeIso } from '../utils/convencoes'

const SUAVE = 'text-[#6e6378] dark:text-[#a093a8]'

interface Props {
  contratos: Contrato[]
  perfis: PerfilJornadaResumo[]
  onTrocar: (contratoId: number, perfil: string) => Promise<void>
  /** Admin de empresa própria: só escolhe a convenção do próprio contrato. */
  modoEscolha?: boolean
}

export const ConvencaoContratos: React.FC<Props> = ({ contratos, perfis, onTrocar, modoEscolha = false }) => {
  const [pendente, setPendente] = useState<{ id: number; perfil: string } | null>(null)
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState<string | null>(null)
  const hoje = hojeIso()

  const porPerfil = new Map(perfis.map((p) => [p.perfil, p]))
  /** Nome para o usuário; o identificador técnico nunca aparece. */
  const nomeDe = (perfil: string, c?: Contrato): string => {
    const p = porPerfil.get(perfil)
    if (p) return p.padrao ? 'Padrão' : p.nome
    return c?.perfil_jornada_nome ?? 'Convenção que você não vê'
  }
  const vencida = (p: PerfilJornadaResumo) =>
    !p.padrao && descreverVigencia(p.vigencia_inicio, p.vigencia_fim, hoje).estado === 'vencida'

  const confirmar = async () => {
    if (!pendente) return
    setSalvando(true)
    setErro(null)
    try {
      await onTrocar(pendente.id, pendente.perfil)
      setPendente(null)
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Erro ao trocar a convenção do contrato')
    } finally {
      setSalvando(false)
    }
  }

  return (
    <section className={`${CARD} overflow-hidden`} aria-labelledby="convencao-contratos">
      <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39]">
        <h2 id="convencao-contratos" className="text-sm font-bold text-[#2d0a33] dark:text-white">
          {modoEscolha ? 'Convenção da empresa' : 'Convenção de cada contrato'}
        </h2>
        <p className={`text-xs mt-0.5 ${SUAVE}`}>
          A troca vale para as análises feitas a partir daí. Lote sem contrato usa o Padrão.
        </p>
      </div>
      <div className="px-5 pt-4 empty:hidden">
        <ErroBox message={erro} />
      </div>
      {contratos.length === 0 ? (
        <p className={`p-5 text-xs ${SUAVE}`}>Nenhum contrato cadastrado.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse min-w-[520px]">
            <thead>
              <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                {!modoEscolha && <th scope="col" className={TH_PLANO}>Tomador</th>}
                {!modoEscolha && <th scope="col" className={TH_PLANO}>Prestador</th>}
                <th scope="col" className={TH_PLANO}>Convenção</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
              {contratos.map((c) => {
                const atual = nomeDe(c.perfil_jornada, c)
                const emTroca = pendente?.id === c.id && pendente.perfil !== c.perfil_jornada
                const rotuloContrato = modoEscolha ? 'a empresa' : `${c.tomador_nome} e ${c.prestador_razao_social}`
                return (
                  <React.Fragment key={c.id}>
                    <tr>
                      {!modoEscolha && <td className={`${TD} font-bold`}>{c.tomador_nome}</td>}
                      {!modoEscolha && <td className={TD}>{c.prestador_razao_social}</td>}
                      <td className={TD}>
                        <select
                          aria-label={`Convenção do contrato de ${rotuloContrato}`}
                          className="px-3 py-1.5 rounded-xl text-sm bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-[#3e0b48] dark:focus-visible:ring-[#f38df9]"
                          value={pendente?.id === c.id ? pendente.perfil : c.perfil_jornada}
                          disabled={salvando}
                          onChange={(e) => {
                            setErro(null)
                            setPendente(e.target.value === c.perfil_jornada ? null : { id: c.id, perfil: e.target.value })
                          }}
                        >
                          {[...perfis]
                            .sort((a, b) => Number(b.padrao) - Number(a.padrao) || a.nome.localeCompare(b.nome, 'pt-BR'))
                            .map((p) => (
                              <option key={p.perfil} value={p.perfil}>
                                {nomeDe(p.perfil)}
                                {vencida(p) ? ' (vencida)' : ''}
                              </option>
                            ))}
                          {!porPerfil.has(c.perfil_jornada) && <option value={c.perfil_jornada}>{atual}</option>}
                        </select>
                      </td>
                    </tr>
                    {emTroca && pendente && (
                      <tr>
                        <td colSpan={modoEscolha ? 1 : 3} className="px-5 pb-4">
                          <div
                            role="alert"
                            className="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-900/50 text-amber-800 dark:text-amber-300 text-xs space-y-2"
                          >
                            <div className="flex items-start gap-2">
                              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" aria-hidden="true" />
                              <span>
                                Trocar de <b>{atual}</b> para <b>{nomeDe(pendente.perfil)}</b> vale para as próximas
                                análises. As análises de ponto já feitas não são refeitas sozinhas: é preciso
                                reprocessar cada documento.
                              </span>
                            </div>
                            <div className="flex gap-2">
                              <button type="button" onClick={confirmar} disabled={salvando} className={BTN_SEC}>
                                {salvando && <Loader2 className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />}
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
    </section>
  )
}
