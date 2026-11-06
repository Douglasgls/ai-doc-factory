import { useState, useEffect, useMemo, useCallback } from 'react'
import { Header } from './components/Header'
import { BackgroundWave } from './components/BackgroundWave'
import { UploadModal } from './components/UploadModal'
import HomePage from './pages/HomePage'
import CategoryPage from './pages/CategoryPage'
import ManualReviewPage from './pages/ManualReviewPage'
import {
  INITIAL_CATEGORIES,
  INITIAL_DETAILED_DOCUMENTS,
  INITIAL_REVIEW_PENDING_DOCUMENTS,
} from './data/mockData'
import type { DocumentCategory, DetailedDocument, ReviewPendingDocument } from './types'
import type { FilterType } from './components/FilterBar'
import { apiService, BASE_URL } from './services/api'

function formatTimeAgo(dateString?: string): string {
  if (!dateString) return 'Recente'
  try {
    const diff = Math.max(0, Date.now() - new Date(dateString).getTime())
    const minutes = Math.floor(diff / 60000)
    if (minutes < 1) return 'Agora mesmo'
    if (minutes < 60) return `Há ${minutes} min`
    const hours = Math.floor(minutes / 60)
    if (hours < 24) return `Há ${hours} h`
    const days = Math.floor(hours / 24)
    return `Há ${days} d`
  } catch {
    return 'Recente'
  }
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

  // Navigation view state: 'home' | 'categoria' | 'revisao'
  const [currentView, setCurrentView] = useState<'home' | 'categoria' | 'revisao'>('home')

  // Data states: inicializa vazio para carregar dados reais da API
  const [categories, setCategories] = useState<DocumentCategory[]>([])
  const [detailedDocs, setDetailedDocs] = useState<DetailedDocument[]>([])
  const [reviewPendingDocs, setReviewPendingDocs] = useState<ReviewPendingDocument[]>([])
  const [isApiLoading, setIsApiLoading] = useState<boolean>(true)
  const [apiErrorMessage, setApiErrorMessage] = useState<string | null>(null)

  // Selected category when in 'categoria' view
  const [selectedCategory, setSelectedCategory] = useState<DocumentCategory | null>(null)

  // Home filtering & search states
  const [categorySearch, setCategorySearch] = useState<string>('')
  const [globalSearch, setGlobalSearch] = useState<string>('')
  const [filterType, setFilterType] = useState<FilterType>('todos')

  // Upload modal state
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)

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

  const toggleTheme = () => {
    setIsDark((prev) => !prev)
  }

  const [refreshTrigger, setRefreshTrigger] = useState(0)

  const refreshData = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1)
  }, [])

  // Carregar dados reais da API
  useEffect(() => {
    let isMounted = true

    const loadData = async () => {
      try {
        console.log('[App] Conectando à API em:', BASE_URL)
        const [tiposRes, docsRes, reviewRes] = await Promise.all([
          apiService.getTipos().catch((err) => {
            console.error('[App] Erro ao carregar /tipos:', err)
            return null
          }),
          apiService.getDocumentos().catch((err) => {
            console.error('[App] Erro ao carregar /documentos:', err)
            return null
          }),
          apiService.getReviewQueue().catch((err) => {
            console.error('[App] Erro ao carregar /revisao:', err)
            return null
          }),
        ])

        if (!isMounted) return

        if (!tiposRes || !docsRes) {
          throw new Error(`Não foi possível carregar os dados da API em ${BASE_URL}`)
        }

        console.log('[App] Dados da API carregados com sucesso:', {
          tipos: tiposRes.length,
          grupos: docsRes.grupos.length,
          revisao: reviewRes?.length || 0,
        })
        setApiErrorMessage(null)

        // 1. Processar categorias e documentos classificados da API
        const gruposMap = new Map(docsRes.grupos.map((g) => [g.tipo, g]))
        const totalDocs = docsRes.grupos.reduce((sum, g) => sum + g.total, 0)

        const parsedCategories: DocumentCategory[] = tiposRes.map((t) => {
          const grupo = gruposMap.get(t.slug)
          const count = grupo ? grupo.total : 0
          return {
            id: t.slug,
            slug: t.slug,
            name: t.nome,
            count,
            totalPercentage: totalDocs > 0 ? Math.round((count / totalDocs) * 100) : 0,
            icon: t.icone || 'file',
          }
        })

        // Incluir categorias adicionais não previstas nos tipos base, caso existam documentos
        for (const g of docsRes.grupos) {
          if (!tiposRes.some((t) => t.slug === g.tipo) && g.total > 0) {
            parsedCategories.push({
              id: g.tipo,
              slug: g.tipo,
              name: g.tipo === 'sem_tipo' ? 'Sem classificação' : g.tipo,
              count: g.total,
              totalPercentage: totalDocs > 0 ? Math.round((g.total / totalDocs) * 100) : 0,
              icon: 'file',
            })
          }
        }

        setCategories(parsedCategories)

        // Achatar documentos detalhados dos grupos
        const allDocs: DetailedDocument[] = []
        for (const g of docsRes.grupos) {
          for (const d of g.documentos) {
            allDocs.push({
              id: String(d.id),
              filename: d.nome_arquivo || `documento_${d.id}.pdf`,
              category: d.tipo || g.tipo,
              personName: d.pessoa || d.campos?.nome || 'Não identificado',
              pages: d.n_paginas || (d.pagina_fim - d.pagina_ini + 1) || 1,
              processedDate: d.processado_em
                ? new Date(d.processado_em).toLocaleDateString('pt-BR')
                : 'Hoje',
              confidence: d.confianca,
              metadata: {
                registrationNumber: d.campos?.matricula || d.campos?.registro || '',
                cpfNumber: d.campos?.cpf || '',
                rgNumber: d.campos?.rg || '',
                address: d.campos?.endereco || '',
                categoryType: d.campos?.categoria || '',
                ...d.campos,
              },
            })
          }
        }
        setDetailedDocs(allDocs)

        // 2. Processar fila de revisão da API
        if (reviewRes) {
          const parsedReviewDocs: ReviewPendingDocument[] = reviewRes.map((r) => {
            const pages =
              r.n_paginas ||
              (r.pagina_fim !== undefined && r.pagina_ini !== undefined
                ? r.pagina_fim - r.pagina_ini + 1
                : 1)
            return {
              id: String(r.id),
              filename: r.nome_arquivo || `documento_${r.id}.pdf`,
              issueType: (r.confianca < 0.7
                ? 'confiança_baixa'
                : 'baixa_qualidade') as ReviewPendingDocument['issueType'],
              issueLabel: r.motivo || 'Revisão necessária',
              timeAgo: formatTimeAgo(r.processado_em),
              isPriority: r.confianca < 0.6,
              processedDate: r.processado_em
                ? new Date(r.processado_em).toLocaleDateString('pt-BR')
                : 'Hoje',
              pages,
              issueDescription:
                r.motivo || `Classificado com ${(r.confianca * 100).toFixed(0)}% de confiança.`,
              suggestedType: r.tipo_sugerido,
              suggestedConfidence: r.confianca,
              extractedFields: Object.entries(r.campos || {}).map(([key, value]) => ({
                key,
                value: String(value),
              })),
              personName: r.pessoa || r.campos?.nome || '',
              imagemUrl: r.imagem_url ? `${BASE_URL}${r.imagem_url}` : undefined,
              loteId: r.lote_id,
              paginaIni: r.pagina_ini,
            }
          })
          setReviewPendingDocs(parsedReviewDocs)
        }
      } catch (err) {
        console.error('[App] Erro na sincronização com a API:', err)
        if (isMounted) {
          setApiErrorMessage(
            err instanceof Error ? err.message : 'Falha na comunicação com a API'
          )
          // Fallback para mock data apenas se houver falha de rede
          setCategories(INITIAL_CATEGORIES)
          setDetailedDocs(INITIAL_DETAILED_DOCUMENTS)
          setReviewPendingDocs(INITIAL_REVIEW_PENDING_DOCUMENTS)
        }
      } finally {
        if (isMounted) {
          setIsApiLoading(false)
        }
      }
    }

    void loadData()

    return () => {
      isMounted = false
    }
  }, [refreshTrigger])

  // Calculate dynamic stats based on state
  const classifiedCount = useMemo(() => {
    return categories.reduce((acc, cat) => acc + cat.count, 0)
  }, [categories])

  const reviewCount = reviewPendingDocs.length

  // Filter categories for the Home view
  const filteredCategories = useMemo(() => {
    return categories.filter((cat) => {
      const matchesSearch =
        cat.name.toLowerCase().includes(categorySearch.toLowerCase()) ||
        cat.slug.toLowerCase().includes(categorySearch.toLowerCase())

      const matchesGlobal =
        !globalSearch ||
        cat.name.toLowerCase().includes(globalSearch.toLowerCase())

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

  // Handle manual review approval with backend API
  const handleApproveReviewDoc = async (
    docId: string,
    finalCategoryNameOrSlug: string,
    personName: string,
    updatedFields?: Record<string, string | null>
  ) => {
    const numId = Number(docId)

    // Find category slug
    const targetCat =
      categories.find(
        (c) =>
          c.slug.toLowerCase() === finalCategoryNameOrSlug.toLowerCase() ||
          c.name.toLowerCase() === finalCategoryNameOrSlug.toLowerCase() ||
          c.id.toLowerCase() === finalCategoryNameOrSlug.toLowerCase()
      ) || categories[0]

    const tipoSlug = targetCat ? targetCat.slug : finalCategoryNameOrSlug

    try {
      // 1. Se campos foram alterados/adicionados, salva via PUT /documentos/{id}/campos
      if (updatedFields && Object.keys(updatedFields).length > 0) {
        await apiService.atualizarCampos(numId, updatedFields, 'Operador')
      }

      // 2. Submete a revisão de classificação via POST /documentos/{id}/revisao
      await apiService.submitReview(numId, tipoSlug, 'Operador')

      // 3. Atualiza os dados da API em tempo real
      refreshData()
    } catch (err) {
      console.error('Falha ao processar revisão via API:', err)

      // Fallback local se a API estiver fora do ar
      const docToApprove = reviewPendingDocs.find((d) => d.id === docId)
      if (!docToApprove) return

      setReviewPendingDocs((prev) => prev.filter((d) => d.id !== docId))

      const newDoc: DetailedDocument = {
        id: `doc-${Date.now()}`,
        filename: docToApprove.filename,
        category: targetCat.id,
        personName: personName || docToApprove.personName || 'Sem nome informado',
        pages: docToApprove.pages,
        processedDate: 'Hoje',
        confidence: 1.0,
        metadata: {
          registrationNumber: '09817263541',
          categoryType: targetCat.id === 'cnh' ? 'B' : undefined,
        },
      }

      setDetailedDocs((prev) => [newDoc, ...prev])

      setCategories((prev) => {
        const next = prev.map((c) =>
          c.id === targetCat.id ? { ...c, count: c.count + 1 } : c
        )
        const newTotal = next.reduce((sum, item) => sum + item.count, 0)
        return next.map((c) => ({
          ...c,
          totalPercentage: newTotal > 0 ? Math.round((c.count / newTotal) * 100) : 0,
        }))
      })
    }
  }

  // Handle upload completion
  const handleUploadSuccess = (filename: string, loteId: number) => {
    console.log(`Lote ${loteId} (${filename}) enviado para processamento.`)
    refreshData()
  }

  // Active documents for the category view
  const categoryDocuments = useMemo(() => {
    if (!selectedCategory) return []
    return detailedDocs.filter(
      (d) =>
        d.category.toLowerCase() === selectedCategory.id.toLowerCase() ||
        d.category.toLowerCase() === selectedCategory.slug.toLowerCase()
    )
  }, [detailedDocs, selectedCategory])

  return (
    <div className="min-h-screen bg-[#fbf9fc] dark:bg-[#140c17] text-[#2d0a33] dark:text-[#f7f3f9] relative font-sans antialiased transition-colors selection:bg-[#9333ea]/30 selection:text-white">
      {/* Bernhoeft background fluid wave */}
      <BackgroundWave />

      {/* Top Navbar */}
      <Header
        isDark={isDark}
        onToggleTheme={toggleTheme}
        onOpenUpload={() => setIsUploadModalOpen(true)}
        onOpenReview={handleOpenReview}
        reviewCount={reviewCount}
        activeTab={currentView === 'revisao' ? 'revisao' : 'documentos'}
        onSelectTab={(tab) => {
          if (tab === 'documentos') {
            handleBackToHome()
          } else if (tab === 'revisao') {
            handleOpenReview()
          }
        }}
        globalSearch={globalSearch}
        onGlobalSearchChange={setGlobalSearch}
      />

      {/* Main Content Area */}
      <main className="max-w-[1440px] mx-auto px-4 sm:px-6 lg:px-8 py-8 sm:py-10 relative z-10">
        {/* Aviso de erro se a API não responder */}
        {apiErrorMessage && (
          <div className="mb-6 p-4 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900/60 text-xs sm:text-sm text-amber-800 dark:text-amber-300 flex items-center justify-between">
            <span>⚠️ {apiErrorMessage} (Exibindo dados de demonstração)</span>
            <button
              onClick={() => refreshData()}
              className="px-3 py-1.5 rounded-lg bg-amber-200 dark:bg-amber-900 text-amber-900 dark:text-amber-100 font-semibold cursor-pointer hover:opacity-90"
            >
              Tentar novamente
            </button>
          </div>
        )}

        {/* Loading inicial da API */}
        {isApiLoading && categories.length === 0 ? (
          <div className="py-24 flex flex-col items-center justify-center gap-3">
            <div className="w-8 h-8 border-3 border-[#9333ea] border-t-transparent rounded-full animate-spin" />
            <span className="text-sm font-medium text-[#6e6378] dark:text-[#a093a8]">
              Carregando documentos da API...
            </span>
          </div>
        ) : (
          <>
            {/* VIEW 1: CATEGORIA ESPECÍFICA */}
            {currentView === 'categoria' && selectedCategory && (
              <CategoryPage
                category={selectedCategory}
                documents={categoryDocuments}
                onBack={handleBackToHome}
              />
            )}

            {/* VIEW 2: REVISÃO MANUAL */}
            {currentView === 'revisao' && (
              <ManualReviewPage
                documents={reviewPendingDocs}
                onBack={handleBackToHome}
                onApprove={handleApproveReviewDoc}
                availableCategories={categories.map((c) => ({ slug: c.slug, name: c.name }))}
              />
            )}

            {/* VIEW 3: HOME PRINCIPAL (Pastas) */}
            {currentView === 'home' && (
              <HomePage
                reviewCount={reviewCount}
                onOpenReview={handleOpenReview}
                classifiedCount={classifiedCount}
                categorySearch={categorySearch}
                onCategorySearchChange={setCategorySearch}
                filterType={filterType}
                onFilterChange={setFilterType}
                filteredCategories={filteredCategories}
                onOpenCategory={handleOpenCategory}
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
      />
    </div>
  )
}

export default App
