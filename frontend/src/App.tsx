import { useState, useEffect, useMemo, useCallback } from 'react'
import { Header } from './components/Header'
import { BackgroundWave } from './components/BackgroundWave'
import { UploadModal } from './components/UploadModal'
import HomePage from './pages/HomePage'
import CategoryPage from './pages/CategoryPage'
import ManualReviewPage from './pages/ManualReviewPage'
import { OFFICIAL_CATEGORY_OPTIONS } from './pages/reviewCategories'
import LoginPage from './pages/LoginPage'
import OrganizacoesPage from './pages/OrganizacoesPage'
import TerceirizadasPage from './pages/TerceirizadasPage'
import EquipePage from './pages/EquipePage'
import AceitarConvitePage from './pages/AceitarConvitePage'
import { estaNaTelaDeConvite } from './utils/convites'
import { FailedDocumentsBanner, type FailedDocument } from './components/FailedDocumentsBanner'
import { LotesStatusPanel } from './components/LotesStatusPanel'
import { trackedStatus } from './hooks/lotePollingLogic'
import { useLotePolling } from './hooks/useLotePolling'
import { apiService, authToken, AUTH_EXPIRED_EVENT, type DocumentoResponse, type UsuarioAtual } from './services/api'
import type { DocumentCategory, DetailedDocument, ReviewPendingDocument, Company } from './types'
import type { FilterType } from './components/FilterBar'
import { podeConvidar, podeEditar, podeEnviar, veConformidade, veOrganizacoes, veTerceirizadas } from './utils/permissoes'

function formatDatePtBr(isoString?: string | null): string {
  if (!isoString) return new Date().toLocaleDateString('pt-BR')
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime())) return new Date().toLocaleDateString('pt-BR')
  return parsed.toLocaleDateString('pt-BR')
}

function formatTimeAgo(isoString?: string | null): string {
  if (!isoString) return 'Recentemente'
  const parsed = new Date(isoString)
  if (Number.isNaN(parsed.getTime())) return 'Recentemente'
  const diffMs = Date.now() - parsed.getTime()
  const diffMinutes = Math.floor(diffMs / 60000)
  if (diffMinutes < 1) return 'Agora mesmo'
  if (diffMinutes < 60) return `Há ${diffMinutes} min`
  const diffHours = Math.floor(diffMinutes / 60)
  if (diffHours < 24) return `Há ${diffHours}h`
  const diffDays = Math.floor(diffHours / 24)
  return diffDays === 1 ? 'Há 1 dia' : `Há ${diffDays} dias`
}

function normalizeCampoKey(rawKey: string): string {
  return rawKey
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 40)
}

export function App() {
  // Theme state: defaults to true (Dark Mode)
  const [isDark, setIsDark] = useState<boolean>(() => {
    const saved = localStorage.getItem('theme')
    if (saved !== null) {
      return saved === 'dark'
    }
    return true // Default dark mode
  })

  // Autenticação: o token fica em sessionStorage; sem ele só o login aparece e nenhuma chamada de dados é feita
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(() => authToken.get() !== null)

  // Navigation view state: 'home' | 'categoria' | 'revisao'
  const [currentView, setCurrentView] = useState<
    'home' | 'categoria' | 'revisao' | 'organizacoes' | 'terceirizadas' | 'equipe'
  >('home')

  // Tela pública de aceite de convite: tem prioridade sobre o login (o token vem no fragmento da URL)
  const [emConvite, setEmConvite] = useState<boolean>(estaNaTelaDeConvite)

  // Usuário logado: o nível decide o que aparece (Organizações e contrato obrigatório no upload)
  const [usuario, setUsuario] = useState<UsuarioAtual | null>(null)

  // Data states
  const [categories, setCategories] = useState<DocumentCategory[]>([])
  const [detailedDocs, setDetailedDocs] = useState<DetailedDocument[]>([])
  const [reviewPendingDocs, setReviewPendingDocs] = useState<ReviewPendingDocument[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [failedDocs, setFailedDocs] = useState<FailedDocument[]>([])
  const [autoClassifiedCount, setAutoClassifiedCount] = useState<number>(0)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Selected category when in 'categoria' view
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory | null>(null)

  // Home filtering & search states
  const [categorySearch, setCategorySearch] = useState<string>('')
  const [globalSearch, setGlobalSearch] = useState<string>('')
  const [filterType, setFilterType] = useState<FilterType>('todos')

  // Upload modal & tracker popover state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [isTrackerOpen, setIsTrackerOpen] = useState(false)

  // Synchronize dark mode class to <html>
  useEffect(() => {
    const root = document.documentElement
    if (isDark) {
      root.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      root.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }, [isDark])

  // Qualquer 401 (token expirado ou inválido) limpa os dados e volta ao login
  useEffect(() => {
    const handleExpired = () => {
      setIsAuthenticated(false)
      setUsuario(null)
      setCategories([])
      setDetailedDocs([])
      setReviewPendingDocs([])
      setCompanies([])
      setFailedDocs([])
      setAutoClassifiedCount(0)
      setSelectedCategory(null)
      setCurrentView('home')
      setIsUploadModalOpen(false)
    }
    window.addEventListener(AUTH_EXPIRED_EVENT, handleExpired)
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleExpired)
  }, [])

  const handleLogout = () => {
    authToken.clear()
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT))
  }

  // Fetch data from backend
  const fetchData = useCallback(async (silent: boolean = false) => {
    // Sem o nível do usuário não se sabe quais rotas chamar (as de conformidade são só da plataforma)
    if (!isAuthenticated || !usuario) return
    if (!silent) {
      setIsLoading(true)
      setError(null)
    }
    try {
      const [tiposData, empresasData, docsAgrupados, reviewData, docsComErro] = await Promise.all([
        apiService.getTipos(),
        veConformidade(usuario) ? apiService.getEmpresas() : Promise.resolve([] as Company[]),
        apiService.getDocumentosAgrupados(undefined, false),
        apiService.getReviewQueue(),
        apiService.getDocumentosAgrupados(undefined, true),
      ])

      // Documentos em estado 'erro' ficam fora das pastas; o aviso garante que não sumam da tela
      setFailedDocs(
        docsComErro.grupos.flatMap((g) =>
          g.documentos.map((d) => ({
            id: d.id,
            loteId: d.lote_id,
            filename: d.nome_arquivo || `Lote ${d.lote_id}`,
            paginaIni: d.pagina_ini,
            paginaFim: d.pagina_fim,
          }))
        )
      )

      setCompanies(empresasData)

      const tipoNameMap = new Map<string, string>()
      tiposData.forEach((t) => tipoNameMap.set(t.slug, t.nome))

      // Filter grouped documents to classified/reviewed ones so pending review docs aren't double-counted
      const gruposPorTipo = new Map<string, DocumentoResponse[]>()
      let autoCount = 0

      docsAgrupados.grupos.forEach((g) => {
        const docsClassificados = g.documentos.filter(
          (d) => d.estado === 'classificado' || d.estado === 'revisado'
        )
        docsClassificados.forEach((d) => {
          if (d.estado === 'classificado') {
            autoCount += 1
          }
        })
        if (g.tipo) {
          gruposPorTipo.set(g.tipo, docsClassificados)
        }
      })

      setAutoClassifiedCount(autoCount)

      // Map official types from GET /tipos into DocumentCategory[]
      const baseCategories: DocumentCategory[] = tiposData.map((t) => {
        const docs = gruposPorTipo.get(t.slug) || []
        return {
          id: t.slug,
          name: t.nome,
          slug: t.slug,
          count: docs.length,
          totalPercentage: 0,
          icon: t.icone || 'file',
        }
      })

      const totalDocs = baseCategories.reduce((acc, cat) => acc + cat.count, 0)
      const categoriesWithPercentage = baseCategories.map((cat) => ({
        ...cat,
        totalPercentage: totalDocs > 0 ? Math.round((cat.count / totalDocs) * 100) : 0,
      }))

      setCategories(categoriesWithPercentage)

      // Keep selectedCategory in sync if user is viewing a category
      setSelectedCategory((prev) =>
        prev ? categoriesWithPercentage.find((c) => c.id === prev.id) || prev : null
      )

      // Flatten all classified/reviewed documents from groups
      const allDocs: DetailedDocument[] = docsAgrupados.grupos.flatMap((g) =>
        g.documentos
          .filter((d) => d.estado === 'classificado' || d.estado === 'revisado')
          .map((d) => {
            const campos = d.campos || {}
            const parsedTime = d.processado_em ? new Date(d.processado_em).getTime() : d.id
            return {
              id: String(d.id),
              loteId: d.lote_id,
              filename: d.nome_arquivo || `Documento #${d.id}`,
              originalFilename: d.nome_original,
              category: d.tipo || 'desconhecido',
              estado: d.estado,
              personName: d.pessoa || campos.nome || 'Não identificado',
              pages: d.n_paginas ?? d.pagina_fim - d.pagina_ini + 1,
              startPage: d.pagina_ini,
              processedDate: formatDatePtBr(d.processado_em),
              processedTimestamp: Number.isNaN(parsedTime) ? d.id : parsedTime,
              confidence: d.confianca ?? 0,
              campos,
              metadata: {
                registrationNumber: campos.matricula || campos.numero_registro || '',
                categoryType: campos.tipo_prazo || campos.categoria || '',
                expirationDate: campos.data_termino || campos.data_exame || campos.data_vencimento || '',
                cpfNumber: campos.cpf || '',
                rgNumber: campos.rg || '',
                address: campos.endereco || '',
                admissionDate: campos.data_admissao || '',
                examDate: campos.data_exame || '',
                companyName: campos.razao_social_prestadora || '',
                companyCnpj: campos.cnpj_prestadora || '',
              },
            }
          })
      )
      setDetailedDocs(allDocs)

      // Map review queue from GET /revisao (mais recentes primeiro)
      const reviewOrdenados = [...reviewData].sort((a, b) => {
        const timeA = a.processado_em ? new Date(a.processado_em).getTime() : 0
        const timeB = b.processado_em ? new Date(b.processado_em).getTime() : 0
        if (timeA !== timeB && !Number.isNaN(timeA) && !Number.isNaN(timeB)) {
          return timeB - timeA
        }
        return b.id - a.id
      })

      const mappedReviewDocs: ReviewPendingDocument[] = reviewOrdenados.map((d) => {
        const campos = d.campos || {}
        const suggestedSlug = d.tipo_sugerido || 'desconhecido'
        const suggestedLabel =
          tipoNameMap.get(suggestedSlug) ||
          (suggestedSlug === 'desconhecido' ? 'Desconhecido' : suggestedSlug)

        return {
          id: String(d.id),
          loteId: d.lote_id,
          filename: d.nome_arquivo || `Documento #${d.id}`,
          issueType: 'confiança_baixa',
          issueLabel: d.motivo || 'Revisão pendente',
          timeAgo: formatTimeAgo(d.processado_em),
          processedDate: formatDatePtBr(d.processado_em),
          processedTimestamp: d.processado_em ? new Date(d.processado_em).getTime() : undefined,
          pages: d.n_paginas ?? d.pagina_fim - d.pagina_ini + 1,
          startPage: d.pagina_ini,
          issueDescription: d.motivo || 'Documento requer verificação manual.',
          suggestedType: suggestedSlug,
          suggestedTypeLabel: suggestedLabel,
          suggestedConfidence: d.confianca ?? 0,
          extractedFields: Object.entries(campos).map(([key, value]) => ({
            key,
            value: String(value),
          })),
          initialCampos: campos,
          personName: d.pessoa || campos.nome || 'Não identificado',
        }
      })
      setReviewPendingDocs(mappedReviewDocs)
    } catch (err) {
      console.error('Erro ao buscar dados:', err)
      if (!silent) {
        setError(
          err instanceof Error && err.message
            ? err.message
            : 'Não foi possível carregar os dados do servidor.'
        )
      }
    } finally {
      if (!silent) {
        setIsLoading(false)
      }
    }
  }, [isAuthenticated, usuario])

  useEffect(() => {
    if (!isAuthenticated) return
    let cancelado = false
    apiService
      .getMe()
      .then((u) => {
        if (!cancelado) setUsuario(u)
      })
      .catch((err) => {
        if (cancelado) return
        setError(err instanceof Error && err.message ? err.message : 'Não foi possível identificar o usuário.')
        setIsLoading(false)
      })
    return () => {
      cancelado = true
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (!isAuthenticated || !usuario) return
    const timer = setTimeout(() => {
      void fetchData(false)
    }, 0)
    return () => clearTimeout(timer)
  }, [isAuthenticated, usuario, fetchData])

  const toggleTheme = () => {
    setIsDark((prev) => !prev)
  }

  // Calculate dynamic stats based on state
  const classifiedCount = useMemo(() => {
    return categories.reduce((acc, cat) => acc + cat.count, 0)
  }, [categories])

  const reviewCount = reviewPendingDocs.length

  const accuracyPercentage = useMemo(() => {
    const totalProcessed = classifiedCount + reviewCount
    if (totalProcessed === 0) return 0
    return Math.round((autoClassifiedCount / totalProcessed) * 100)
  }, [autoClassifiedCount, classifiedCount, reviewCount])

  // Filter categories for the Home view
  const filteredCategories = useMemo(() => {
    return categories.filter((cat) => {
      const matchesSearch =
        cat.name.toLowerCase().includes(categorySearch.toLowerCase()) ||
        cat.slug.toLowerCase().includes(categorySearch.toLowerCase())

      const matchesGlobal =
        !globalSearch ||
        cat.name.toLowerCase().includes(globalSearch.toLowerCase()) ||
        cat.slug.toLowerCase().includes(globalSearch.toLowerCase())

      if (filterType === 'com_documentos') {
        return matchesSearch && matchesGlobal && cat.count > 0
      }
      if (filterType === 'vazios') {
        return matchesSearch && matchesGlobal && cat.count === 0
      }
      return matchesSearch && matchesGlobal
    })
  }, [categories, categorySearch, globalSearch, filterType])

  // Open category page
  const handleOpenCategory = (category: DocumentCategory) => {
    setSelectedCategory(category)
    setCurrentView('categoria')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Open manual review page
  const handleOpenReview = () => {
    setCurrentView('revisao')
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Back to home view
  const handleBackToHome = () => {
    setCurrentView('home')
    setSelectedCategory(null)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  // Handle manual review approval
  const handleApproveReviewDoc = async (
    docId: string,
    finalCategorySlugOrName: string,
    personName: string,
    updatedFields?: { key: string; value: string }[],
    initialCampos?: Record<string, string>
  ) => {
    try {
      // Resolve category slug strictly to one of the 7 official backend types
      const matchedCat =
        categories.find(
          (c) =>
            c.slug === finalCategorySlugOrName ||
            c.name.toLowerCase() === finalCategorySlugOrName.toLowerCase()
        ) ||
        OFFICIAL_CATEGORY_OPTIONS.find(
          (c) =>
            c.slug === finalCategorySlugOrName ||
            c.name.toLowerCase() === finalCategorySlugOrName.toLowerCase()
        )
      const targetSlug = matchedCat
        ? matchedCat.slug
        : OFFICIAL_CATEGORY_OPTIONS.some((c) => c.slug === finalCategorySlugOrName)
          ? finalCategorySlugOrName
          : OFFICIAL_CATEGORY_OPTIONS[0].slug

      // Build campos update payload only for fields that were added, modified, or removed.
      // Never re-send masked identifiers ('cpf', 'rg', 'pis' containing '*') because the backend rejects masked values.
      const camposPayload: Record<string, string | null> = {}
      const seenKeys = new Set<string>()
      const normalizedInitial: Record<string, string> = {}

      if (initialCampos) {
        Object.entries(initialCampos).forEach(([k, v]) => {
          const nk = normalizeCampoKey(k)
          if (nk) normalizedInitial[nk] = String(v).trim()
        })
      }

      if (updatedFields) {
        updatedFields.forEach(({ key, value }) => {
          const normKey = normalizeCampoKey(key)
          const trimmedVal = value.trim()
          if (normKey && trimmedVal) {
            seenKeys.add(normKey)
            const isMaskedIdentifier =
              (normKey === 'cpf' || normKey === 'rg' || normKey === 'pis') &&
              trimmedVal.includes('*')
            const isUnchanged = normalizedInitial[normKey] === trimmedVal
            if (!isMaskedIdentifier && !isUnchanged) {
              camposPayload[normKey] = trimmedVal
            }
          }
        })
      }

      const trimmedPerson = personName.trim()
      if (trimmedPerson && trimmedPerson !== 'Não identificado') {
        seenKeys.add('nome')
        if (normalizedInitial['nome'] !== trimmedPerson && !trimmedPerson.includes('*')) {
          camposPayload['nome'] = trimmedPerson
        }
      }

      Object.keys(normalizedInitial).forEach((normOrig) => {
        if (normOrig && !seenKeys.has(normOrig)) {
          camposPayload[normOrig] = null
        }
      })

      if (Object.keys(camposPayload).length > 0) {
        await apiService.updateDocumentCampos(
          Number(docId),
          camposPayload,
          'Revisor Humano'
        )
      }

      await apiService.submitReview(Number(docId), targetSlug, 'Revisor Humano')

      // Optimistically remove from pending queue and refresh full state from backend
      setReviewPendingDocs((prev) => prev.filter((d) => d.id !== docId))
      await fetchData(true)
    } catch (err) {
      console.error('Erro ao aprovar documento:', err)
      alert(
        err instanceof Error
          ? err.message
          : 'Erro ao processar a aprovação do documento.'
      )
    }
  }

  // Acompanha cada lote enviado via SSE (tempo real) + fallback polling e atualiza a lista
  const refreshSilently = useCallback(() => fetchData(true), [fetchData])
  const {
    lotes: lotesEnviados,
    track: trackLote,
    uploadFiles: uploadLotes,
    cancel: cancelLote,
    retry: retryLote,
    recheck: recheckLote,
    dismiss: dismissLote,
    dismissAcaoErro: dismissAcaoErroLote,
    clearFinished: clearFinishedLotes,
  } = useLotePolling(refreshSilently)

  const handleNavigateCategoryBySlug = (slug: string) => {
    const matched = categories.find((c) => c.slug === slug || c.id === slug)
    if (matched) {
      handleOpenCategory(matched)
    }
  }

  const handleUploadSuccess = (filename: string, loteId: number) => {
    void fetchData(true)
    trackLote(loteId, filename)
    setIsTrackerOpen(true)
  }

  const handleUploadFiles = (selectedFiles: File[], contratoId: number | null) => {
    setIsTrackerOpen(true)
    uploadLotes(selectedFiles, contratoId)
  }

  // Active documents for the category view
  const categoryDocuments = useMemo(() => {
    if (!selectedCategory) return []
    return detailedDocs.filter((d) => d.category === selectedCategory.id)
  }, [detailedDocs, selectedCategory])

  const availableCategoryOptions = useMemo(() => {
    return categories.map((c) => ({ slug: c.slug, name: c.name }))
  }, [categories])

  if (emConvite) {
    return (
      <div className="min-h-screen bg-[#fbf9fc] dark:bg-[#140c17] text-[#2d0a33] dark:text-[#f7f3f9] relative font-sans antialiased transition-colors">
        <BackgroundWave />
        <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8 relative z-10">
          <AceitarConvitePage
            onSuccess={() => {
              // Já havia sessão de outra conta nesta aba: recarrega para não misturar com o usuário antigo
              if (isAuthenticated) {
                window.location.replace('/')
                return
              }
              setCurrentView('home')
              setIsAuthenticated(true)
              setEmConvite(false)
            }}
          />
        </main>
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-[#fbf9fc] dark:bg-[#140c17] text-[#2d0a33] dark:text-[#f7f3f9] relative font-sans antialiased transition-colors">
        <BackgroundWave />
        <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8 relative z-10">
          <LoginPage onSuccess={() => setIsAuthenticated(true)} />
        </main>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#fbf9fc] dark:bg-[#140c17] text-[#2d0a33] dark:text-[#f7f3f9] relative font-sans antialiased transition-colors selection:bg-[#9333ea]/30 selection:text-white">
      {/* Background fluid wave */}
      <BackgroundWave />

      {/* Top Navbar */}
      <Header
        isDark={isDark}
        onToggleTheme={toggleTheme}
        onLogout={handleLogout}
        onOpenUpload={() => setIsUploadModalOpen(true)}
        onOpenReview={handleOpenReview}
        reviewCount={reviewCount}
        activeTab={
          currentView === 'revisao' || currentView === 'organizacoes' || currentView === 'terceirizadas' || currentView === 'equipe'
            ? currentView
            : 'documentos'
        }
        showOrganizacoes={veOrganizacoes(usuario)}
        showTerceirizadas={veTerceirizadas(usuario)}
        showEquipe={podeConvidar(usuario)}
        mostrarEnvio={podeEnviar(usuario)}
        onSelectTab={(tab) => {
          if (tab === 'documentos') {
            handleBackToHome()
          } else if (tab === 'revisao') {
            handleOpenReview()
          } else {
            setCurrentView(tab)
            window.scrollTo({ top: 0, behavior: 'smooth' })
          }
        }}
        globalSearch={globalSearch}
        onGlobalSearchChange={setGlobalSearch}
        lotes={lotesEnviados}
        isTrackerOpen={isTrackerOpen}
        onToggleTracker={() => setIsTrackerOpen((prev) => !prev)}
        onMinimizeTracker={() => setIsTrackerOpen(false)}
        onCancelLote={(id) => void cancelLote(id)}
        onRetryLote={(id) => void retryLote(id)}
        onRecheckLote={recheckLote}
        onDismissLote={dismissLote}
        onDismissAcaoErroLote={dismissAcaoErroLote}
        onClearFinishedLotes={clearFinishedLotes}
        onNavigateCategory={handleNavigateCategoryBySlug}
      />

      {/* Main Content Area */}
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 relative z-10">
        <LotesStatusPanel
          lotes={lotesEnviados.filter((l) => {
            const s = trackedStatus(l)
            return s === 'erro' || s === 'cancelado' || s === 'timeout' || Boolean(l.networkError) || Boolean(l.acaoErro)
          })}
          onRecheck={recheckLote}
          onDismiss={dismissLote}
          onDismissAcaoErro={dismissAcaoErroLote}
          onRetry={(id) => void retryLote(id)}
        />
        {!isLoading && !error && <FailedDocumentsBanner documents={failedDocs} />}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-12 h-12 border-4 border-[#9333ea] border-t-transparent rounded-full animate-spin"></div>
            <p className="text-[#6e6378] dark:text-[#a093a8] font-medium">
              Carregando dados do servidor...
            </p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4 text-center">
            <div className="w-16 h-16 bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-[#2d0a33] dark:text-white">{error}</h3>
            <button
              onClick={() => fetchData(false)}
              className="px-6 py-2 bg-[#9333ea] text-white rounded-xl font-bold hover:bg-[#7e22ce] transition-colors cursor-pointer"
            >
              Tentar novamente
            </button>
          </div>
        ) : (
          <>
            {/* VIEW 1: CATEGORIA ESPECÍFICA */}
            {currentView === 'categoria' && selectedCategory && (
              <CategoryPage
                category={selectedCategory}
                categories={categories}
                onSelectCategory={handleOpenCategory}
                documents={categoryDocuments}
                onBack={handleBackToHome}
              />
            )}

            {/* VIEW 2: REVISÃO MANUAL */}
            {currentView === 'revisao' && podeEditar(usuario) && (
              <ManualReviewPage
                documents={reviewPendingDocs}
                onBack={handleBackToHome}
                onApprove={handleApproveReviewDoc}
                availableCategories={availableCategoryOptions}
              />
            )}

            {currentView === 'organizacoes' && veOrganizacoes(usuario) && (
              <OrganizacoesPage onBack={handleBackToHome} />
            )}

            {currentView === 'terceirizadas' && veTerceirizadas(usuario) && (
              <TerceirizadasPage onBack={handleBackToHome} />
            )}

            {currentView === 'equipe' && usuario && podeConvidar(usuario) && (
              <EquipePage usuario={usuario} onBack={handleBackToHome} />
            )}

            {/* VIEW 3: HOME PRINCIPAL (Pastas) */}
            {currentView === 'home' && (
              <HomePage
                reviewCount={reviewCount}
                onOpenReview={podeEditar(usuario) ? handleOpenReview : undefined}
                classifiedCount={classifiedCount}
                accuracyPercentage={accuracyPercentage}
                categorySearch={categorySearch}
                onCategorySearchChange={setCategorySearch}
                filterType={filterType}
                onFilterChange={setFilterType}
                filteredCategories={filteredCategories}
                onOpenCategory={handleOpenCategory}
                companies={companies}
              />
            )}
          </>
        )}
      </main>

      {/* Upload Modal */}
      <UploadModal
        isOpen={isUploadModalOpen}
        onClose={() => setIsUploadModalOpen(false)}
        onSuccessUpload={handleUploadSuccess}
        onUploadFiles={handleUploadFiles}
        contratoObrigatorio={usuario?.nivel === 'prestador'}
      />
    </div>
  )
}

export default App
