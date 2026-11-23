import React, { useState } from 'react'
import { FileText } from 'lucide-react'
import ConformidadeEmpresaModal from '../components/ConformidadeEmpresaModal'
import ConformidadeEmpresasLista from '../components/ConformidadeEmpresasLista'
import { tomadoresDoPrestador } from '../utils/contratos'
import type { Contrato } from '../services/api'
import { ManualReviewBanner } from '../components/ManualReviewBanner'
import { MetricsCard } from '../components/MetricsCard'
import { FilterBar, type FilterType } from '../components/FilterBar'
import { FolderCard } from '../components/FolderCard'
import type { DocumentCategory, Company } from '../types'

interface HomePageProps {
  reviewCount: number
  /** Ausente para quem não pode revisar (tomador): o aviso de revisão não aparece. */
  onOpenReview?: () => void
  classifiedCount: number
  accuracyPercentage: number
  categorySearch: string
  onCategorySearchChange: (value: string) => void
  filterType: FilterType
  onFilterChange: (value: FilterType) => void
  filteredCategories: DocumentCategory[]
  onOpenCategory: (category: DocumentCategory) => void
  companies: Company[]
  /** Empresa solo: títulos neutros, sem termos de terceirização. */
  empresaPropria?: boolean
  /** Contratos do usuário da terceirizada; mostram o tomador sob o nome de cada empresa. Vazio para os demais. */
  contratos?: Contrato[]
}

const HomePage: React.FC<HomePageProps> = ({
  reviewCount,
  onOpenReview,
  classifiedCount,
  accuracyPercentage,
  categorySearch,
  onCategorySearchChange,
  filterType,
  onFilterChange,
  filteredCategories,
  onOpenCategory,
  companies,
  empresaPropria = false,
  contratos = [],
}) => {
  const [selecionada, setSelecionada] = useState<Company | null>(null)
  return (
    <div className="space-y-6 sm:space-y-8 animate-in fade-in duration-200">
      {/* Page Title & Subtitle */}
      <section className="flex items-start sm:items-center gap-3.5">
        <div className="w-11 h-11 rounded-2xl bg-purple-100 dark:bg-purple-950/60 text-[#9333ea] dark:text-[#f38df9] flex items-center justify-center shrink-0 border border-purple-200/60 dark:border-purple-800/40 shadow-xs mt-0.5 sm:mt-0">
          <FileText className="w-5 h-5" />
        </div>
        <div className="space-y-1">
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#fdfcfe]">
            {empresaPropria ? 'Seus documentos' : 'Documentos'}
          </h1>
          <p className="text-sm sm:text-base text-[#6f6379] dark:text-[#9f91a6]">
            Documentos processados pela IA, organizados por tipo documental.
          </p>
        </div>
      </section>

      {/* Manual Review Attention Banner */}
      {reviewCount > 0 && onOpenReview && (
        <section>
          <ManualReviewBanner
            count={reviewCount}
            onReviewClick={onOpenReview}
          />
        </section>
      )}

      {/* Global Metrics Summary Card */}
      <section>
        <MetricsCard
          classifiedCount={classifiedCount}
          accuracyPercentage={accuracyPercentage}
          reviewCount={reviewCount}
        />
      </section>

      {/* Category Search & Filter Tabs */}
      <section className="pt-2">
        <FilterBar
          searchCategory={categorySearch}
          onSearchChange={onCategorySearchChange}
          activeFilter={filterType}
          onFilterChange={onFilterChange}
        />
      </section>

      {/* Document Folders Grid - Foco baseado na movimentação do mouse */}
      <section className="space-y-4">
        <h2 className="text-xl font-bold text-[#2d0a33] dark:text-[#fdfcfe] flex items-center gap-2">
          <span>Tipos Documentais</span>
          <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-[#f3e8ff] dark:bg-[#2e1065] text-[#7e22ce] dark:text-[#d8b4fe]">
            {filteredCategories.length}
          </span>
        </h2>
        {filteredCategories.length === 0 ? (
          <div className="w-full py-16 text-center rounded-2xl border border-dashed border-[#dcd4e2] dark:border-[#33203e] bg-white/50 dark:bg-[#1a1120]/50">
            <p className="text-base font-semibold text-[#2d0a33] dark:text-white">
              Nenhuma categoria encontrada
            </p>
            <p className="text-xs text-[#8f8298] dark:text-[#7f7188] mt-1">
              Tente buscar por outro termo ou limpe os filtros.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-5 sm:gap-6 auto-rows-fr">
            {filteredCategories.map((category) => (
              <FolderCard
                key={category.id}
                category={category}
                isSelected={false}
                onClick={onOpenCategory}
              />
            ))}
          </div>
        )}
      </section>

      {/* Company Compliance Section */}
      {companies.length > 0 && (
        <section className="space-y-4 pt-4">
          <h2 className="text-xl font-bold text-[#2d0a33] dark:text-[#fdfcfe] flex items-center gap-2">
            <span>Conformidade por Empresa</span>
            <span className="text-xs font-normal px-2 py-0.5 rounded-full bg-[#ecfdf5] dark:bg-[#064e3b] text-[#059669] dark:text-[#6ee7b7]">
              {companies.length}
            </span>
          </h2>
          
          <ConformidadeEmpresasLista
            companies={companies}
            onSelect={setSelecionada}
            tomadoresPorCnpj={(cnpj) => tomadoresDoPrestador(contratos, cnpj)}
          />
        </section>
      )}

      {selecionada && (
        <ConformidadeEmpresaModal
          cnpj={selecionada.cnpj}
          razaoSocial={selecionada.razao_social}
          onClose={() => setSelecionada(null)}
          empresaPropria={empresaPropria}
        />
      )}
    </div>
  )
}

export default HomePage
