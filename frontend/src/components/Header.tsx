import React, { useEffect, useRef, useState } from 'react'
import { Briefcase, Building2, Clock, FileText, LogOut, Menu, Moon, Sun, Users, X, type LucideIcon } from 'lucide-react'
import { ProcessingTrackerPopover } from './ProcessingTrackerPopover'
import { EviDocsBrand } from './EviDocsBrand'
import { BuscaDocumentos } from './BuscaDocumentos'
import type { TrackedLote } from '../hooks/lotePollingLogic'

interface HeaderProps {
  isDark: boolean
  onToggleTheme: () => void
  onLogout: () => void
  onOpenUpload: () => void
  onOpenReview: () => void
  reviewCount: number
  activeTab: 'documentos' | 'revisao' | 'organizacoes' | 'perfis' | 'terceirizadas' | 'equipe'
  onSelectTab: (tab: 'documentos' | 'revisao' | 'organizacoes' | 'perfis' | 'terceirizadas' | 'equipe') => void
  /** Só o nível plataforma vê a tela de Organizações. */
  showOrganizacoes?: boolean
  /** Convenções coletivas (perfis de jornada da análise de ponto). */
  showPerfis?: boolean
  /** Administrador do cliente (tomador) cadastra terceirizadas. */
  showTerceirizadas?: boolean
  /** Empresa solo: rótulos sem termos de terceirização. */
  empresaPropria?: boolean
  /** Administradores de qualquer nível veem a equipe e convidam colegas. */
  showEquipe?: boolean
  /** Tomador é somente leitura: sem botão Enviar nem acompanhamento de envios. */
  mostrarEnvio?: boolean
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

type Aba = HeaderProps['activeTab']

const CLASSE_ATIVA = 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9]'
const CLASSE_INATIVA =
  'text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'

export const Header: React.FC<HeaderProps> = ({
  isDark,
  onToggleTheme,
  onLogout,
  onOpenUpload,
  onOpenReview,
  //reviewCount,
  activeTab,
  onSelectTab,
  showOrganizacoes = false,
  showPerfis = false,
  showTerceirizadas = false,
  empresaPropria = false,
  showEquipe = false,
  mostrarEnvio = true,
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
  const itens: { tab: Aba; rotulo: string; icone: LucideIcon }[] = [
    { tab: 'documentos', rotulo: empresaPropria ? 'Seus documentos' : 'Documentos', icone: FileText },
    ...(showOrganizacoes ? [{ tab: 'organizacoes' as const, rotulo: 'Organizações', icone: Building2 }] : []),
    ...(showPerfis ? [{ tab: 'perfis' as const, rotulo: 'Convenções coletivas', icone: Clock }] : []),
    ...(showTerceirizadas ? [{ tab: 'terceirizadas' as const, rotulo: 'Terceirizadas', icone: Briefcase }] : []),
    ...(showEquipe ? [{ tab: 'equipe' as const, rotulo: 'Equipe', icone: Users }] : []),
  ]

  const [menuAberto, setMenuAberto] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuBotaoRef = useRef<HTMLButtonElement>(null)
  const primeiroItemRef = useRef<HTMLButtonElement>(null)

  // Aberto, o foco vai para o primeiro item; Esc ou clique fora fecham.
  useEffect(() => {
    if (!menuAberto) return
    primeiroItemRef.current?.focus()
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMenuAberto(false)
        menuBotaoRef.current?.focus()
      }
    }
    const aoClicarFora = (e: MouseEvent) => {
      const alvo = e.target as Element
      // O visualizador aberto por um resultado da busca fica fora do menu, mas não deve fechá-lo.
      if (menuRef.current && !menuRef.current.contains(alvo) && !alvo.closest?.('[data-visualizador-busca]')) {
        setMenuAberto(false)
      }
    }
    document.addEventListener('keydown', aoTeclar)
    document.addEventListener('mousedown', aoClicarFora)
    return () => {
      document.removeEventListener('keydown', aoTeclar)
      document.removeEventListener('mousedown', aoClicarFora)
    }
  }, [menuAberto])

  // Se a janela passar de 640px com o menu aberto, ele fecha.
  useEffect(() => {
    const consulta = window.matchMedia('(min-width: 640px)')
    const aoMudar = () => {
      if (consulta.matches) setMenuAberto(false)
    }
    consulta.addEventListener('change', aoMudar)
    return () => consulta.removeEventListener('change', aoMudar)
  }, [])

  const escolherItem = (tab: Aba) => {
    setMenuAberto(false)
    menuBotaoRef.current?.focus()
    onSelectTab(tab)
  }

  return (
    <header className="w-full border-b border-[#ece8ef] dark:border-[#27192f] bg-white/90 dark:bg-[#140c17]/90 backdrop-blur-md sticky top-0 z-30 transition-colors">
      <div className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        {/* Left: Logo & Navigation Tabs */}
        <div className="flex items-center gap-2 sm:gap-8 min-w-0">
          {/* Marca EviDocs */}
          <div className="flex items-center gap-2 cursor-pointer select-none" onClick={() => onSelectTab('documentos')}>
            <EviDocsBrand sizeClass="text-xl sm:text-2xl" />
          </div>

          {/* Navigation Tabs: a partir de 640px ficam na barra; abaixo disso, no menu */}
          <nav aria-label="Principal" className="hidden sm:flex items-center gap-2">
            {itens.map((item) => (
              <button
                key={item.tab}
                type="button"
                onClick={() => onSelectTab(item.tab)}
                title={item.rotulo}
                aria-label={item.rotulo}
                aria-current={activeTab === item.tab ? 'page' : undefined}
                className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all inline-flex items-center gap-1.5 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea] ${
                  activeTab === item.tab ? CLASSE_ATIVA : CLASSE_INATIVA
                }`}
              >
                <item.icone className="w-4 h-4" aria-hidden="true" />
                <span className="hidden lg:inline">{item.rotulo}</span>
              </button>
            ))}
          </nav>

          {/* Menu do celular */}
          <div ref={menuRef} className="relative sm:hidden">
            <button
              ref={menuBotaoRef}
              type="button"
              onClick={() => setMenuAberto((aberto) => !aberto)}
              aria-expanded={menuAberto}
              aria-controls="menu-navegacao"
              aria-label="Menu"
              className="p-2 rounded-lg text-[#6e6378] dark:text-[#d3c7dc] hover:bg-[#f3edf6] dark:hover:bg-[#281831] transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea]"
            >
              {menuAberto ? <X className="w-5 h-5" aria-hidden="true" /> : <Menu className="w-5 h-5" aria-hidden="true" />}
            </button>
            {menuAberto && (
              <div
                id="menu-navegacao"
                className="absolute left-0 top-[calc(100%+8px)] w-[min(20rem,calc(100vw-2rem))] rounded-xl border border-[#e6dfec] dark:border-[#2a1d32] bg-white dark:bg-[#140d18] shadow-xl p-1.5 z-50"
              >
                <BuscaDocumentos variante="menu" empresaPropria={empresaPropria} />
                {itens.map((item, indice) => (
                  <button
                    key={item.tab}
                    ref={indice === 0 ? primeiroItemRef : undefined}
                    type="button"
                    onClick={() => escolherItem(item.tab)}
                    aria-current={activeTab === item.tab ? 'page' : undefined}
                    className={`w-full px-3 py-2.5 rounded-lg text-sm font-medium text-left inline-flex items-center gap-2.5 cursor-pointer focus-visible:outline-2 focus-visible:outline-[#9333ea] ${
                      activeTab === item.tab ? CLASSE_ATIVA : CLASSE_INATIVA
                    }`}
                  >
                    <item.icone className="w-4 h-4 shrink-0" aria-hidden="true" />
                    {item.rotulo}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right: Search, Upload Button & Theme Toggle */}
        <div className="flex items-center gap-1.5 sm:gap-4 shrink-0">
          {/* Busca por texto: a partir de 640px fica na barra; abaixo disso, dentro do menu */}
          <div className="hidden sm:block">
            <BuscaDocumentos variante="barra" empresaPropria={empresaPropria} />
          </div>

          {/* Upload Button / Real-time Processing Tracker Bubble */}
          {mostrarEnvio && (
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
          )}

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

