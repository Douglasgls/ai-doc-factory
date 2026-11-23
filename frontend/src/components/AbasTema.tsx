import React, { useRef } from 'react'
import { AlertCircle } from 'lucide-react'
import { idAba, idPainel } from '../utils/abas'

export interface AbaDef {
  id: string
  rotulo: string
  /** Quantidade ao lado do nome; some quando é 0. */
  contagem?: number
  /** Aviso vermelho de campo com erro. */
  erro?: boolean
}

interface Props {
  /** Prefixo dos ids, para ligar a aba ao painel. */
  base: string
  rotulo: string
  abas: AbaDef[]
  ativa: string
  onChange: (id: string) => void
}


/** Faixa de abas: setas, Home e End trocam de aba; no celular a faixa rola na horizontal dentro dela mesma. */
export const AbasTema: React.FC<Props> = ({ base, rotulo, abas, ativa, onChange }) => {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({})

  const mover = (e: React.KeyboardEvent, i: number) => {
    const n = abas.length
    const alvo =
      e.key === 'ArrowRight' ? (i + 1) % n : e.key === 'ArrowLeft' ? (i - 1 + n) % n : e.key === 'Home' ? 0 : e.key === 'End' ? n - 1 : null
    if (alvo === null) return
    e.preventDefault()
    const id = abas[alvo].id
    onChange(id)
    refs.current[id]?.focus()
  }

  return (
    <div className="max-w-full min-w-0 overflow-x-auto overscroll-x-contain border-b border-[#ebe5ef] dark:border-[#2f1e39]">
      <div role="tablist" aria-label={rotulo} className="flex flex-nowrap gap-1 w-max min-w-full px-2">
        {abas.map((a, i) => {
          const sel = a.id === ativa
          return (
            <button
              key={a.id}
              ref={(el) => {
                refs.current[a.id] = el
              }}
              type="button"
              role="tab"
              id={idAba(base, a.id)}
              aria-selected={sel}
              aria-controls={idPainel(base, a.id)}
              tabIndex={sel ? 0 : -1}
              onClick={() => onChange(a.id)}
              onKeyDown={(e) => mover(e, i)}
              className={`shrink-0 whitespace-nowrap px-3 py-2.5 text-sm font-semibold border-b-2 -mb-px cursor-pointer inline-flex items-center gap-1.5 focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#9333ea] rounded-t-lg transition-colors ${
                sel
                  ? 'border-[#3e0b48] dark:border-[#f38df9] text-[#3e0b48] dark:text-[#f38df9]'
                  : 'border-transparent text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'
              }`}
            >
              {a.rotulo}
              {!!a.contagem && <span className="tabular-nums">· {a.contagem}</span>}
              {a.erro && (
                <>
                  <AlertCircle className="w-3.5 h-3.5 text-red-600 dark:text-red-400" aria-hidden="true" />
                  <span className="sr-only">: há campo com erro</span>
                </>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
