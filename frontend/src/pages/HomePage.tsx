import React, { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import ConformidadeEmpresaModal from '../components/ConformidadeEmpresaModal'
import { formatarCnpjVisual } from '../components/conformidadeEmpresa'
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
}) => {
  const [selecionada, setSelecionada] = useState<Company | null>(null)
  return (
    <div className="space-y-6 sm:space-y-8 animate-in fade-in duration-200">
      {/* Page Title & Subtitle */}
      <section className="space-y-1">
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#fdfcfe]">
          Documentos
        </h1>
        <p className="text-sm sm:text-base text-[#6f6379] dark:text-[#9f91a6]">
          Documentos processados pela IA, organizados por tipo documental.
        </p>
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
          
          <div className="overflow-hidden rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-sm">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <th className="px-6 py-4 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider">Empresa</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider">CNPJ</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider">Status</th>
                  <th className="px-6 py-4 text-xs font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider text-right">Score</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                {companies.map((company) => (
                  <tr
                    key={company.cnpj}
                    onClick={() => setSelecionada(company)}
                    className="hover:bg-[#fdfbfe] dark:hover:bg-[#251831] transition-colors cursor-pointer"
                  >
                    <td className="px-6 py-4">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelecionada(company)
                        }}
                        aria-label={`Ver como a nota de ${company.razao_social} foi calculada`}
                        className="text-left text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc] hover:underline focus-visible:outline-2 focus-visible:outline-[#9333ea] rounded cursor-pointer"
                      >
                        {company.razao_social}
                      </button>
                      <div className="flex items-center gap-2 mt-0.5">
                        {company.provisorio && (
                          <span
                            title="Esta nota ainda pode mudar: há documentos não analisados ou critérios sem nada para avaliar. Abra os detalhes para ver o motivo."
                            className="text-[10px] text-[#9333ea] dark:text-[#d67bf3] font-medium italic cursor-help"
                          >
                            Score provisório
                            <span className="sr-only">: esta nota ainda pode mudar; abra os detalhes para ver o motivo.</span>
                          </span>
                        )}
                        <span className="text-[10px] text-[#6e6378] dark:text-[#a093a8] inline-flex items-center gap-0.5">
                          Ver como a nota foi calculada <ChevronRight className="w-3 h-3" aria-hidden="true" />
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4 text-sm text-[#6e6378] dark:text-[#a093a8] font-mono">
                      {formatarCnpjVisual(company.cnpj)}
                    </td>
                    <td className="px-6 py-4">
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                        company.classificacao == null ? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300' :
                        company.classificacao === 'Regular' ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400' :
                        company.classificacao === 'Atenção' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                        'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                      }`}>
                        {company.classificacao ?? 'Sem nota'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                        <div className="w-16 h-2 bg-[#f3e8ff] dark:bg-[#2e1065] rounded-full overflow-hidden hidden sm:block">
                          <div 
                            className={`h-full rounded-full ${
                              company.score >= 85 ? 'bg-emerald-500' :
                              company.score >= 65 ? 'bg-amber-500' :
                              'bg-red-500'
                            }`}
                            style={{ width: `${company.score}%` }}
                          />
                        </div>
                        <span className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc]">
                          {company.score == null ? '—' : `${company.score}%`}
                        </span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {selecionada && (
        <ConformidadeEmpresaModal
          cnpj={selecionada.cnpj}
          razaoSocial={selecionada.razao_social}
          onClose={() => setSelecionada(null)}
        />
      )}
    </div>
  )
}

export default HomePage
