import React from 'react'
import { Sun, Moon, LogOut } from 'lucide-react'
import { ProcessingTrackerPopover } from './ProcessingTrackerPopover'
import type { TrackedLote } from '../hooks/lotePollingLogic'
// import { Search } from 'lucide-react'

interface HeaderProps {
  isDark: boolean
  onToggleTheme: () => void
  onLogout: () => void
  onOpenUpload: () => void
  onOpenReview: () => void
  reviewCount: number
  activeTab: 'documentos' | 'revisao'
  onSelectTab: (tab: 'documentos' | 'revisao') => void
  globalSearch: string
  onGlobalSearchChange: (value: string) => void
  lotes?: TrackedLote[]
  isTrackerOpen?: boolean
  onToggleTracker?: () => void
  onMinimizeTracker?: () => void
  onCancelLote?: (id: number) => void
  onRetryLote?: (id: number) => void
  onRecheckLote?: (id: number) => void
  onDismissLote?: (id: number) => void
  onDismissAcaoErroLote?: (id: number) => void
  onClearFinishedLotes?: () => void
  onNavigateCategory?: (slug: string) => void
}

export const Header: React.FC<HeaderProps> = ({
  isDark,
  onToggleTheme,
  onLogout,
  onOpenUpload,
  onOpenReview,
  //reviewCount,
  activeTab,
  onSelectTab,
  // globalSearch,
  // onGlobalSearchChange,
  lotes = [],
  isTrackerOpen = false,
  onToggleTracker = () => {},
  onMinimizeTracker = () => {},
  onCancelLote = () => {},
  onRetryLote = () => {},
  onRecheckLote = () => {},
  onDismissLote = () => {},
  onDismissAcaoErroLote = () => {},
  onClearFinishedLotes = () => {},
  onNavigateCategory,
}) => {
  return (
    <header className="w-full border-b border-[#ece8ef] dark:border-[#27192f] bg-white/90 dark:bg-[#140c17]/90 backdrop-blur-md sticky top-0 z-30 transition-colors">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Logo & Navigation Tabs */}
        <div className="flex items-center gap-6 sm:gap-8">
          {/* Marca EviDocs */}
          <div className="flex items-center gap-2 cursor-pointer select-none" onClick={() => onSelectTab('documentos')}>
            <span className="font-extrabold text-xl tracking-tight text-[#2d0a33] dark:text-white">
              EviDocs
            </span>
          </div>

          {/* Navigation Tabs */}
          <nav className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => onSelectTab('documentos')}
              className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all ${
                activeTab === 'documentos'
                  ? 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9]'
                  : 'text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'
              }`}
            >
              Documentos
            </button>

            {/* 
            <button
              type="button"
              onClick={onOpenReview}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all flex items-center gap-2 ${
                activeTab === 'revisao'
                  ? 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9]'
                  : 'text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'
              }`}
            >
              <span>Revisão manual</span>
              {reviewCount > 0 && (
                <span className="bg-[#e11d48] text-white text-[11px] font-bold w-4 h-4 rounded-full flex items-center justify-center shadow-xs">
                  {reviewCount}
                </span>
              )}
            </button>
            */}
          </nav>
        </div>

        {/* Right: Search, Upload Button & Theme Toggle */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Global Search Input (Comentado temporariamente)
          <div className="relative hidden md:block">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8f8298] dark:text-[#83748d]" />
            <input
              type="text"
              placeholder="Buscar em todos os documentos"
              value={globalSearch}
              onChange={(e) => onGlobalSearchChange(e.target.value)}
              className="w-64 lg:w-72 pl-10 pr-4 py-1.5 text-sm rounded-lg bg-[#f8f6fa] dark:bg-[#1d1222] border border-[#e5dfec] dark:border-[#311f3d] text-[#2d0a33] dark:text-[#f5edf9] placeholder-[#8f8298] dark:placeholder-[#776881] focus:outline-none focus:ring-1 focus:ring-[#9333ea] dark:focus:ring-[#c026d3] transition-all"
            />
          </div>
          */}

          {/* Upload Button / Real-time Processing Tracker Bubble */}
          <ProcessingTrackerPopover
            lotes={lotes}
            isOpen={isTrackerOpen}
            onToggleOpen={onToggleTracker}
            onMinimize={onMinimizeTracker}
            onOpenUpload={onOpenUpload}
            onCancel={onCancelLote}
            onRetry={onRetryLote}
            onRecheck={onRecheckLote}
            onDismiss={onDismissLote}
            onDismissAcaoErro={onDismissAcaoErroLote}
            onClearFinished={onClearFinishedLotes}
            onNavigateCategory={onNavigateCategory}
            onNavigateReview={onOpenReview}
          />

          {/* Theme Toggle (Dark / Light) */}
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label="Alternar tema"
            title={isDark ? 'Mudar para modo claro' : 'Mudar para modo escuro'}
            className="p-2 rounded-lg text-[#6e6378] dark:text-[#d3c7dc] hover:bg-[#f3edf6] dark:hover:bg-[#281831] transition-colors cursor-pointer"
          >
            {isDark ? (
              <Sun className="w-5 h-5 text-amber-300 hover:text-amber-200 transition-colors" />
            ) : (
              <Moon className="w-5 h-5 text-[#3e0b48] hover:text-[#52105e] transition-colors" />
            )}
          </button>

          {/* Sair */}
          <button
            type="button"
            onClick={onLogout}
            aria-label="Sair"
            title="Sair"
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-[#6e6378] dark:text-[#d3c7dc] hover:bg-[#f3edf6] dark:hover:bg-[#281831] transition-colors cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sair</span>
          </button>
        </div>
      </div>
    </header>
  )
}

