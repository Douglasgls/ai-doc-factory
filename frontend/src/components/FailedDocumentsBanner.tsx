import React from 'react'
import { AlertTriangle } from 'lucide-react'

export interface FailedDocument {
  id: number
  loteId: number
  filename: string
  paginaIni: number
  paginaFim: number
}

interface FailedDocumentsBannerProps {
  documents: FailedDocument[]
}

const MAX_LISTED = 8

export const FailedDocumentsBanner: React.FC<FailedDocumentsBannerProps> = ({ documents }) => {
  const count = documents.length
  if (count <= 0) return null
  const listed = documents.slice(0, MAX_LISTED)

  return (
    <div
      className="w-full rounded-2xl border p-4 sm:p-5 mb-6 bg-white dark:bg-[#1a1120] border-[#ebe5ef] dark:border-[#2f1e39] shadow-xs"
      data-testid="documentos-erro"
    >
      <div className="flex items-center gap-3.5 sm:gap-4 min-w-0">
        <div className="relative shrink-0">
          <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400">
            <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 stroke-[2]" />
          </div>
          <span className="absolute -top-1 -right-1 bg-[#dc2626] text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center shadow-xs">
            {count}
          </span>
        </div>
        <div className="min-w-0">
          <h3 className="text-sm sm:text-base font-semibold text-[#2d0a33] dark:text-[#f8f5fc] leading-snug">
            {count === 1 ? '1 documento falhou no processamento' : `${count} documentos falharam no processamento`}
          </h3>
          <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#9f91a6] mt-0.5">
            {count === 1 ? 'Ele não aparece' : 'Eles não aparecem'} nas pastas nem na fila de revisão.
          </p>
        </div>
      </div>
      <ul className="mt-3 space-y-1 text-xs sm:text-sm text-[#6e6378] dark:text-[#9f91a6]">
        {listed.map((d) => (
          <li key={d.id} className="break-words">
            Lote {d.loteId} ({d.filename}),{' '}
            {d.paginaIni === d.paginaFim ? `página ${d.paginaIni}` : `páginas ${d.paginaIni} a ${d.paginaFim}`}
          </li>
        ))}
        {count > listed.length && <li>e mais {count - listed.length} documento(s)</li>}
      </ul>
    </div>
  )
}
