import React from 'react'
import { AlertCircle, CheckCircle2 } from 'lucide-react'

/** Classes e blocos de formulário compartilhados pelas telas de cadastro. */
export const CARD =
  'rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-sm'
export const INPUT =
  'w-full px-3 py-2 rounded-xl text-sm bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white placeholder-[#8f8298] focus:outline-none focus:ring-1 focus:ring-[#9333ea] read-only:opacity-70'
export const LABEL = 'block text-xs font-semibold text-[#2d0a33] dark:text-white mb-1'
export const BTN =
  'px-5 py-2 rounded-xl text-sm font-bold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer'
export const BTN_SEC =
  'px-3 py-1.5 rounded-lg text-xs font-bold text-[#5c1363] dark:text-[#f38df9] bg-[#f4e8f7] dark:bg-[#34163d] hover:opacity-80 disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer'
export const TH =
  'px-5 py-3 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider'
export const TD = 'px-5 py-3 text-sm text-[#2d0a33] dark:text-[#f8f5fc]'

export const ErroBox: React.FC<{ message: string | null }> = ({ message }) =>
  message ? (
    <div
      role="alert"
      className="p-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/50 flex items-center gap-2 text-red-600 dark:text-red-400"
    >
      <AlertCircle className="w-4 h-4 shrink-0" />
      <span className="text-xs font-medium">{message}</span>
    </div>
  ) : null

const CORES = {
  verde: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  cinza: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  ambar: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
}

export const Selo: React.FC<{ tom: keyof typeof CORES; children: React.ReactNode }> = ({ tom, children }) => (
  <span className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${CORES[tom]}`}>{children}</span>
)

/** Componente de feedback visual imediato para status do e-mail digitado. */
export const EmailStatusFeedback: React.FC<{ email: string; valido: boolean; id?: string }> = ({
  email,
  valido,
  id,
}) => {
  const v = email.trim()
  if (!v) return null
  if (valido) {
    return (
      <div id={id} className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400 mt-1.5">
        <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
        <span>E-mail válido</span>
      </div>
    )
  }
  return (
    <div
      id={id}
      role="alert"
      className="flex items-center gap-1.5 text-xs font-medium text-rose-600 dark:text-rose-400 mt-1.5"
    >
      <AlertCircle className="w-3.5 h-3.5 shrink-0" />
      <span>E-mail incompleto ou inválido (ex: usuario@empresa.com.br)</span>
    </div>
  )
}
