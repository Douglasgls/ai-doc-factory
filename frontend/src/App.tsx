import { useState, useEffect, useMemo } from 'react'
import { Header } from './components/Header'
import { BackgroundWave } from './components/BackgroundWave'
import { UploadModal } from './components/UploadModal'
import HomePage from './pages/HomePage'
import CategoryPage from './pages/CategoryPage'
import ManualReviewPage from './pages/ManualReviewPage'
import LoginPage from './pages/LoginPage'
import { apiService, authToken, AUTH_EXPIRED_EVENT } from './services/api'
import type { DocumentCategory, DetailedDocument, ReviewPendingDocument, Company } from './types'
import type { FilterType } from './components/FilterBar'

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
  const [currentView, setCurrentView] = useState<'home' | 'categoria' | 'revisao'>('home')

  // Data states
  const [categories, setCategories] = useState<DocumentCategory[]>([])
  const [detailedDocs, setDetailedDocs] = useState<DetailedDocument[]>([])
  const [reviewPendingDocs, setReviewPendingDocs] = useState<ReviewPendingDocument[]>([])
  const [companies, setCompanies] = useState<Company[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

  // Qualquer 401 (token expirado ou inválido) limpa os dados e volta ao login
  useEffect(() => {
    const handleExpired = () => {
      setIsAuthenticated(false)
      setCategories([])
      setDetailedDocs([])
      setReviewPendingDocs([])
      setCompanies([])
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
  useEffect(() => {
    if (!isAuthenticated) return
    const fetchData = async () => {
      setIsLoading(true)
      setError(null)
      try {
        const [empresasData, docsAgrupados] = await Promise.all([
          apiService.getEmpresas(),
          apiService.getDocumentosAgrupados()
        ])

        setCompanies(empresasData)

        // Map backend groups to DocumentCategory
        const mappedCategories: DocumentCategory[] = docsAgrupados.grupos.map((g: any) => {
          const id = g.tipo || 'desconhecido'
          const icons: Record<string, DocumentCategory['icon']> = {
            cnh: 'car',
            cpf: 'hash',
            rg: 'idcard',
            folha_ponto: 'file',
            holerite: 'briefcase',
            residencia: 'home',
          }

          return {
            id,
            name: id.toUpperCase().replace('_', ' '),
            slug: id,
            count: g.total,
            totalPercentage: 0, // Will be calculated after
            icon: icons[id] || 'file'
          }
        })

        const totalDocs = mappedCategories.reduce((acc, cat) => acc + cat.count, 0)
        const categoriesWithPercentage = mappedCategories.map(cat => ({
          ...cat,
          totalPercentage: totalDocs > 0 ? Math.round((cat.count / totalDocs) * 100) : 0
        }))

        setCategories(categoriesWithPercentage)

        // Flatten all documents from groups
        const allDocs: DetailedDocument[] = docsAgrupados.grupos.flatMap((g: any) => 
          g.documentos.map((d: any) => ({
            id: String(d.id),
            filename: d.nome_arquivo,
            category: d.tipo || 'desconhecido',
            personName: d.pessoa || 'Não identificado',
            pages: d.n_paginas,
            processedDate: new Date(d.processado_em).toLocaleDateString('pt-BR'),
            confidence: d.confianca,
            metadata: {
              registrationNumber: d.campos?.numero_registro || d.campos?.cpf || '',
              categoryType: d.campos?.categoria || '',
              expirationDate: d.campos?.data_vencimento || '',
            }
          }))
        )
        setDetailedDocs(allDocs)

        // Fetch review queue
        const reviewData = await apiService.getReviewQueue()
        const mappedReviewDocs: ReviewPendingDocument[] = reviewData.map((d: any) => ({
          id: String(d.id),
          loteId: d.lote_id,
          filename: d.nome_arquivo || `Documento #${d.id}`,
          issueType: 'confiança_baixa',
          issueLabel: d.motivo_revisao || 'Revisão Pendente',
          timeAgo: 'Recentemente',
          processedDate: new Date(d.criado_em).toLocaleDateString('pt-BR'),
          pages: (d.pagina_fim - d.pagina_ini) + 1,
          startPage: d.pagina_ini,
          issueDescription: d.motivo_revisao || 'Documento requer verificação manual.',
          suggestedType: d.tipo || 'Desconhecido',
          suggestedConfidence: d.confianca,
          extractedFields: Object.entries(d.campos || {}).map(([key, value]) => ({ key, value: String(value) })),
          personName: d.pessoa || 'Não identificado'
        }))
        setReviewPendingDocs(mappedReviewDocs)

      } catch (err) {
        console.error('Erro ao buscar dados:', err)
        setError('Não foi possível carregar os dados do servidor.')
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [isAuthenticated])

  const toggleTheme = () => {
    setIsDark((prev) => !prev)
  }

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

  // Handle manual review approval
  const handleApproveReviewDoc = async (
    docId: string,
    finalCategoryName: string,
    personName: string
  ) => {
    try {
      await apiService.submitReview(Number(docId), finalCategoryName, 'Revisor Humano')
      
      // Remove from pending queue
      setReviewPendingDocs((prev) => prev.filter((d) => d.id !== docId))

      // Refresh data to show the new document in its category
      const docsAgrupados = await apiService.getDocumentosAgrupados()
      
      // Update categories count and percentage
      const mappedCategories: DocumentCategory[] = docsAgrupados.grupos.map((g: any) => {
        const id = g.tipo || 'desconhecido'
        const icons: Record<string, DocumentCategory['icon']> = {
          cnh: 'car',
          cpf: 'hash',
          rg: 'idcard',
          folha_ponto: 'file',
          holerite: 'briefcase',
          residencia: 'home',
        }

        return {
          id,
          name: id.toUpperCase().replace('_', ' '),
          slug: id,
          count: g.total,
          totalPercentage: 0,
          icon: icons[id] || 'file'
        }
      })

      const totalDocs = mappedCategories.reduce((acc, cat) => acc + cat.count, 0)
      const categoriesWithPercentage = mappedCategories.map(cat => ({
        ...cat,
        totalPercentage: totalDocs > 0 ? Math.round((cat.count / totalDocs) * 100) : 0
      }))
      setCategories(categoriesWithPercentage)

      // Update detailed documents
      const allDocs: DetailedDocument[] = docsAgrupados.grupos.flatMap((g: any) => 
        g.documentos.map((d: any) => ({
          id: String(d.id),
          filename: d.nome_arquivo,
          category: d.tipo || 'desconhecido',
          personName: d.pessoa || 'Não identificado',
          pages: d.n_paginas,
          processedDate: new Date(d.processado_em).toLocaleDateString('pt-BR'),
          confidence: d.confianca,
          metadata: {
            registrationNumber: d.campos?.numero_registro || d.campos?.cpf || '',
            categoryType: d.campos?.categoria || '',
            expirationDate: d.campos?.data_vencimento || '',
          }
        }))
      )
      setDetailedDocs(allDocs)
    } catch (err) {
      console.error('Erro ao aprovar documento:', err)
      alert('Erro ao processar a aprovação do documento.')
    }
  }

  // Handle upload completion
  const handleUploadSuccess = (filename: string, loteId: number) => {
    console.log(`Lote ${loteId} (${filename}) enviado para processamento.`)
    // Aqui poderíamos iniciar um polling para verificar o status do lote
    // Por enquanto, apenas notificamos o sucesso no console
  }

  // Active documents for the category view
  const categoryDocuments = useMemo(() => {
    if (!selectedCategory) return []
    return detailedDocs.filter((d) => d.category === selectedCategory.id)
  }, [detailedDocs, selectedCategory])

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
      {/* Bernhoeft background fluid wave */}
      <BackgroundWave />

      {/* Top Navbar */}
      <Header
        isDark={isDark}
        onToggleTheme={toggleTheme}
        onLogout={handleLogout}
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
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4">
            <div className="w-12 h-12 border-4 border-[#9333ea] border-t-transparent rounded-full animate-spin"></div>
            <p className="text-[#6e6378] dark:text-[#a093a8] font-medium">Carregando dados do servidor...</p>
          </div>
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4 text-center">
            <div className="w-16 h-16 bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400 rounded-full flex items-center justify-center">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
              </svg>
            </div>
            <h3 className="text-xl font-bold text-[#2d0a33] dark:text-white">{error}</h3>
            <button 
              onClick={() => window.location.reload()}
              className="px-6 py-2 bg-[#9333ea] text-white rounded-xl font-bold hover:bg-[#7e22ce] transition-colors"
            >
              Tentar novamente
            </button>
          </div>
        ) : (
          <>
            {/* VIEW 1: CATEGORIA ESPECÍFICA (Ex: CNH) */}
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
                availableCategories={categories.map((c) => c.name)}
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
      />
    </div>
  )
}

export default App
