import React from 'react'
import { INPUT } from './formUi'
import type { TipoCampo } from '../utils/convencoes'
import type { Entrada } from '../utils/convencaoForm'

const PEQUENO = `${INPUT} !w-20 text-right tabular-nums`

const Sufixo: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="text-sm text-[#6e6378] dark:text-[#a093a8]">{children}</span>
)

interface Props {
  id: string
  tipo: TipoCampo
  rotulo: string
  valor: Entrada
  onChange: (v: Entrada) => void
  /** Id do texto de erro, para leitores de tela. */
  erroId?: string
  invalido?: boolean
  autoFocus?: boolean
}

/** Campo na unidade natural do parâmetro: horas e minutos, minutos e segundos, horário ou percentual. */
export const CampoValor: React.FC<Props> = ({ id, tipo, rotulo, valor, onChange, erroId, invalido, autoFocus }) => {
  const comum = { 'aria-invalid': invalido || undefined, 'aria-describedby': erroId }
  const set = (campo: keyof Entrada) => (e: React.ChangeEvent<HTMLInputElement>) => onChange({ ...valor, [campo]: e.target.value })

  if (tipo === 'horario') {
    return (
      <input
        id={id}
        type="time"
        aria-label={rotulo}
        className={`${INPUT} !w-32 tabular-nums`}
        value={valor.horario}
        onChange={set('horario')}
        autoFocus={autoFocus}
        {...comum}
      />
    )
  }
  if (tipo === 'percentual') {
    return (
      <span className="inline-flex items-center gap-1.5">
        <input
          id={id}
          inputMode="decimal"
          aria-label={rotulo}
          className={PEQUENO}
          value={valor.pct}
          onChange={set('pct')}
          autoFocus={autoFocus}
          {...comum}
        />
        <Sufixo>%</Sufixo>
      </span>
    )
  }
  const dois = tipo === 'duracao_seg' ? (['m', 's'] as const) : (['h', 'm'] as const)
  const sufixos = tipo === 'duracao_seg' ? ['min', 's'] : ['h', 'min']
  return (
    <span className="inline-flex items-center gap-1.5" role="group" aria-label={rotulo}>
      <input
        id={id}
        inputMode="numeric"
        aria-label={`${rotulo}: ${sufixos[0] === 'h' ? 'horas' : 'minutos'}`}
        className={PEQUENO}
        value={valor[dois[0]]}
        onChange={set(dois[0])}
        autoFocus={autoFocus}
        {...comum}
      />
      <Sufixo>{sufixos[0]}</Sufixo>
      <input
        inputMode="numeric"
        aria-label={`${rotulo}: ${sufixos[1] === 'min' ? 'minutos' : 'segundos'}`}
        className={PEQUENO}
        value={valor[dois[1]]}
        onChange={set(dois[1])}
        {...comum}
      />
      <Sufixo>{sufixos[1]}</Sufixo>
    </span>
  )
}
