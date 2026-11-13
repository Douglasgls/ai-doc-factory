import React from 'react'
import { AlertTriangle, ChevronRight } from 'lucide-react'

interface ManualReviewBannerProps {
  count: number
  onReviewClick: () => void
}

export const ManualReviewBanner: React.FC<ManualReviewBannerProps> = ({
  count,
  onReviewClick,
}) => {
  if (count <= 0) return null

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onReviewClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onReviewClick()
        }
      }}
      className="group w-full rounded-2xl border transition-all duration-200 p-4 sm:p-5 flex items-center justify-between gap-4 bg-white dark:bg-[#1a1120] border-[#ebe5ef] dark:border-[#2f1e39] hover:border-[#c026d3]/40 dark:hover:border-[#c026d3]/50 shadow-xs hover:shadow-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c2c91]/40"
    >
      <div className="flex items-center gap-3.5 sm:gap-4 min-w-0">
        {/* Warning Icon with badge */}
        <div className="relative shrink-0">
          <div className="w-10 h-10 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center bg-[#f7edf9] dark:bg-[#2a1633] text-[#9333ea] dark:text-[#d67bf3]">
            <AlertTriangle className="w-5 h-5 sm:w-6 sm:h-6 stroke-[2]" />
          </div>
          <span className="absolute -top-1 -right-1 bg-[#dc2626] text-white text-[10px] font-bold w-4 h-4 rounded-full flex items-center justify-center shadow-xs">
            {count}
          </span>
        </div>

        {/* Text descriptions (sem o tom amarelo / marrom) */}
        <div className="min-w-0">
          <h3 className="text-sm sm:text-base font-semibold text-[#2d0a33] dark:text-[#f8f5fc] leading-snug">
            {count} documentos aguardam revisão manual
          </h3>
          <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#9f91a6] mt-0.5 truncate sm:whitespace-normal">
            A IA não conseguiu classificá-los com segurança e eles precisam de análise manual.
          </p>
        </div>
      </div>

      {/* Action button */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation()
          onReviewClick()
        }}
        className="shrink-0 flex items-center gap-1 text-sm font-semibold text-[#9333ea] dark:text-[#d67bf3] group-hover:text-[#7823c4] hover:text-[#7823c4] dark:group-hover:text-[#f38df9] dark:hover:text-[#f38df9] transition-colors cursor-pointer"
      >
        <span>Revisar</span>
        <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
      </button>
    </div>
  )
}
