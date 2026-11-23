import React, { useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Pencil } from 'lucide-react'
import type { ParametroEfetivo, PerfilJornadaDetalhe } from '../services/api'
import { BTN_SEC, CARD, Selo } from './formUi'
import { ReguaDoDia } from './ReguaDoDia'
import { AbasTema, type AbaDef } from './AbasTema'
import { idAba, idPainel } from '../utils/abas'
import {
  GRUPOS,
  descreverVigencia,
  diferencasPorGrupo,
  fraseValor,
  frasePorData,
  hojeIso,
  valoresIguais,
  type DefParametro,
} from '../utils/perfisJornadaFormato'
import { parametrosDoDia } from '../utils/reguaDia'

const TOM_VIGENCIA = {
  sem_prazo: 'cinza',
  vigente: 'verde',
  vence_em_breve: 'ambar',
  vencida: 'ambar',
  futura: 'cinza',
} as const

export const VigenciaSelo: React.FC<{ inicio: string | null; fim: string | null }> = ({ inicio, fim }) => {
  const v = descreverVigencia(inicio, fim, hojeIso())
  const alerta = v.estado === 'vencida' || v.estado === 'vence_em_breve'
  return (
    <Selo tom={TOM_VIGENCIA[v.estado]}>
      {alerta && <AlertTriangle className="w-3 h-3 mr-1 self-center" aria-hidden="true" />}
      {v.texto}
    </Selo>
  )
}

const valoresBase = (efetivo: Record<string, ParametroEfetivo>): Record<string, number> =>
  Object.fromEntries(Object.entries(efetivo).map(([k, v]) => [k, v.valor]))

const SUAVE = 'text-[#6e6378] dark:text-[#a093a8]'
const ABA_DIFERENCAS = 'diferencas'

interface Props {
  detalhe: PerfilJornadaDetalhe
  padrao: PerfilJornadaDetalhe
  /** Texto do escopo ("Geral", "De ...", "Só plataforma"); só a plataforma o vê. */
  escopo?: string
  onEditar?: () => void
  onVoltar: () => void
}

export const DetalhePerfilJornada: React.FC<Props> = ({ detalhe, padrao, escopo, onEditar, onVoltar }) => {
  const ehPadrao = detalhe.padrao
  const atual = useMemo(() => parametrosDoDia(valoresBase(detalhe.efetivo)), [detalhe])
  const ref = useMemo(() => parametrosDoDia(valoresBase(padrao.efetivo)), [padrao])
  const difs = useMemo(() => diferencasPorGrupo(detalhe.efetivo, padrao.efetivo), [detalhe, padrao])
  const [aba, setAba] = useState<string>(ehPadrao ? GRUPOS[0].id : ABA_DIFERENCAS)
  const abas: AbaDef[] = [
    ...(ehPadrao ? [] : [{ id: ABA_DIFERENCAS, rotulo: 'Diferenças do Padrão' }]),
    ...GRUPOS.map((g) => ({ id: g.id, rotulo: g.titulo, contagem: ehPadrao ? 0 : difs[g.id] })),
  ]
  const grupo = GRUPOS.find((g) => g.id === aba)
  const gruposComDiferenca = GRUPOS.map((g) => ({
    ...g,
    parametros: g.parametros.filter((p) => detalhe.efetivo[p.chave] && !valoresIguais(detalhe.efetivo[p.chave], padrao.efetivo[p.chave])),
  })).filter((g) => g.parametros.length > 0)

  return (
    <div className="space-y-5">
      <div className={`${CARD} p-5`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-lg font-bold text-[#2d0a33] dark:text-white">{ehPadrao ? 'Padrão' : detalhe.nome}</h2>
            {ehPadrao ? (
              <p className={`text-sm mt-0.5 ${SUAVE}`}>CLT e Portaria MTP 671/2021. É a referência e não pode ser editada.</p>
            ) : (
              detalhe.sindicato && <p className={`text-sm mt-0.5 ${SUAVE}`}>{detalhe.sindicato}</p>
            )}
            {!ehPadrao && (
              <div className="flex flex-wrap items-center gap-2 mt-3">
                <VigenciaSelo inicio={detalhe.vigencia_inicio} fim={detalhe.vigencia_fim} />
                {escopo && <Selo tom="cinza">{escopo}</Selo>}
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            {!ehPadrao && detalhe.editavel && onEditar && (
              <button type="button" onClick={onEditar} className={BTN_SEC}>
                <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
                Editar
              </button>
            )}
            <button type="button" onClick={onVoltar} className={BTN_SEC}>
              <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
              Voltar
            </button>
          </div>
        </div>
      </div>

      {atual && (
        <div className={`${CARD} p-5`}>
          <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white mb-3">Um dia de trabalho</h3>
          <ReguaDoDia atual={atual} padrao={ehPadrao ? null : ref} />
        </div>
      )}

      <div className="space-y-4">
        <AbasTema base="detalhe" rotulo="Regras por tema" abas={abas} ativa={aba} onChange={setAba} />
        <div
          role="tabpanel"
          id={idPainel('detalhe', aba)}
          aria-labelledby={idAba('detalhe', aba)}
          tabIndex={0}
          className="space-y-4 rounded-xl focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea]"
        >
          {aba === ABA_DIFERENCAS ? (
            gruposComDiferenca.length === 0 ? (
              <p className={`${CARD} p-5 text-sm text-[#2d0a33] dark:text-[#f8f5fc]`}>Esta convenção segue o Padrão em tudo.</p>
            ) : (
              gruposComDiferenca.map((g) => (
                <Grupo key={g.id} id={`dif-${g.id}`} titulo={g.titulo} parametros={g.parametros} detalhe={detalhe} padrao={padrao} />
              ))
            )
          ) : (
            grupo && <Grupo id={`tema-${grupo.id}`} titulo={grupo.titulo} parametros={grupo.parametros} detalhe={detalhe} padrao={padrao} />
          )}
        </div>
      </div>
    </div>
  )
}

const Grupo: React.FC<{
  id: string
  titulo: string
  parametros: DefParametro[]
  detalhe: PerfilJornadaDetalhe
  padrao: PerfilJornadaDetalhe
}> = ({ id, titulo, parametros, detalhe, padrao }) => {
  const ehPadrao = detalhe.padrao
  const linhas = parametros.filter((p) => detalhe.efetivo[p.chave])
  if (linhas.length === 0) return null
  // a base legal do Padrão aparece uma vez, no rodapé, para os parâmetros que a convenção não muda
  const rodape = [
    ...new Set(
      linhas
        .filter((p) => ehPadrao || valoresIguais(detalhe.efetivo[p.chave], padrao.efetivo[p.chave]))
        .map((p) => padrao.efetivo[p.chave]?.base_legal)
        .filter((b): b is string => !!b),
    ),
  ]

  return (
    <section className={`${CARD} p-5`} aria-labelledby={`grupo-${id}`}>
      <h3 id={`grupo-${id}`} className="text-sm font-bold text-[#2d0a33] dark:text-white">
        {titulo}
      </h3>
      <dl className="mt-2 divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
        {linhas.map((p) => {
          const ef = detalhe.efetivo[p.chave]
          const pad = padrao.efetivo[p.chave]
          const igual = !ehPadrao && valoresIguais(ef, pad)
          return (
            <div
              key={p.chave}
              className="py-3 grid gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,0.9fr)]"
            >
              <dt className="text-sm text-[#2d0a33] dark:text-[#f8f5fc]">{p.rotulo}</dt>
              <dd className="m-0 min-w-0">
                <span className={`text-sm tabular-nums ${igual ? SUAVE : 'font-bold text-[#2d0a33] dark:text-white'}`}>
                  {fraseValor(p.chave, ef.valor)}
                </span>
                {!igual && !ehPadrao && ef.base_legal && <p className={`text-xs mt-0.5 ${SUAVE}`}>{ef.base_legal}</p>}
                {(ef.vigencias ?? []).map((v) => (
                  <p key={v.desde} className={`text-xs mt-0.5 tabular-nums ${SUAVE}`}>
                    {frasePorData(p.chave, v.desde, v.valor)}
                  </p>
                ))}
              </dd>
              {!ehPadrao && (
                <dd className={`m-0 text-xs sm:text-right tabular-nums ${SUAVE}`}>
                  {igual ? 'igual ao Padrão' : `Padrão: ${fraseValor(p.chave, pad?.valor ?? 0)}`}
                </dd>
              )}
            </div>
          )
        })}
      </dl>
      {rodape.length > 0 && (
        <p className={`text-xs mt-2 pt-2 border-t border-[#ebe5ef] dark:border-[#2f1e39] ${SUAVE}`}>
          Base legal do Padrão: {rodape.join('; ')}
        </p>
      )}
    </section>
  )
}
