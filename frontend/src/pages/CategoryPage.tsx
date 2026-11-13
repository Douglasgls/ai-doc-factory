import React, { useState, useMemo } from 'react'
import { Search, ChevronLeft, ChevronDown, FileText, ClipboardCheck, ChevronRight } from 'lucide-react'
import type { DocumentCategory, DetailedDocument } from '../types'
import AuditoriaPontoModal from '../components/AuditoriaPontoModal'

interface CategoryPageProps {
  category: DocumentCategory
  documents: DetailedDocument[]
  onBack: () => void
}

const CategoryPage: React.FC<CategoryPageProps> = ({
  category,
  documents,
  onBack,
}) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [selectedPerson, setSelectedPerson] = useState('todas')
  const [selectedConfidence, setSelectedConfidence] = useState('todas')
  const [sortBy, setSortBy] = useState<'recentes' | 'antigos' | 'confianca'>('recentes')
  const [auditDoc, setAuditDoc] = useState<{ id: number; filename: string } | null>(null)

  // Get unique person names for the dropdown
  const peopleList = useMemo(() => {
    const names = new Set(documents.map((d) => d.personName))
    return Array.from(names)
  }, [documents])

  // Filter documents based on inputs
  const filteredDocuments = useMemo(() => {
    const filtered = documents.filter((doc) => {
      // Search query across filename, personName, metadata, and extracted campos
      const query = searchTerm.toLowerCase()
      const matchesSearch =
        !query ||
        doc.filename.toLowerCase().includes(query) ||
        doc.personName.toLowerCase().includes(query) ||
        Object.values(doc.metadata).some(
          (val) => val && val.toLowerCase().includes(query)
        ) ||
        Object.values(doc.campos || {}).some(
          (val) => val && String(val).toLowerCase().includes(query)
        )

      // Person filter
      const matchesPerson =
        selectedPerson === 'todas' || doc.personName === selectedPerson

      // Confidence filter
      let matchesConfidence = true
      if (selectedConfidence === 'alta') {
        matchesConfidence = doc.confidence >= 0.85
      } else if (selectedConfidence === 'media') {
        matchesConfidence = doc.confidence >= 0.7 && doc.confidence < 0.85
      } else if (selectedConfidence === 'baixa') {
        matchesConfidence = doc.confidence < 0.7
      }

      return matchesSearch && matchesPerson && matchesConfidence
    })

    return [...filtered].sort((a, b) => {
      if (sortBy === 'confianca') {
        return b.confidence - a.confidence
      }
      const timeA = a.processedTimestamp ?? Number(a.id)
      const timeB = b.processedTimestamp ?? Number(b.id)
      return sortBy === 'recentes' ? timeB - timeA : timeA - timeB
    })
  }, [documents, searchTerm, selectedPerson, selectedConfidence, sortBy])

  const campoLabels: Record<string, string> = {
    cpf: 'CPF',
    matricula: 'Matrícula',
    data_admissao: 'Admissão',
    data_exame: 'Data do exame',
    data_termino: 'Término',
    tipo_prazo: 'Prazo',
    razao_social_prestadora: 'Empresa',
    cnpj_prestadora: 'CNPJ',
  }

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Breadcrumbs */}
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer"
        >
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
          {category.name}
        </span>
      </nav>

      {/* Header: Title, Count & Action Buttons */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#f8f5fc]">
            {category.name}
          </h1>
          <p className="text-sm text-[#6e6378] dark:text-[#a093a8] mt-1">
            {filteredDocuments.length} documento{filteredDocuments.length !== 1 ? 's' : ''}
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-sm font-medium border border-[#e1d9e6] dark:border-[#35223e] bg-white dark:bg-[#1a1120] hover:bg-[#f8f5fa] dark:hover:bg-[#25162a] text-[#2d0a33] dark:text-[#eae0ee] shadow-2xs transition-colors cursor-pointer"
          >
            <ChevronLeft className="w-4 h-4" />
            <span>Voltar</span>
          </button>
        </div>
      </div>

      {/* Search Input for Category */}
      <div className="relative w-full">
        <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8f8298] dark:text-[#7f7188]" />
        <input
          type="text"
          placeholder={`Buscar em ${category.name}: arquivo, pessoa, número...`}
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full pl-11 pr-4 py-2.5 text-sm rounded-xl bg-white dark:bg-[#1a1120] border border-[#ebe5ef] dark:border-[#2f1e39] text-[#2d0a33] dark:text-[#f5edf9] placeholder-[#8f8298] dark:placeholder-[#776881] focus:outline-none focus:ring-1 focus:ring-[#9333ea] dark:focus:ring-[#c026d3] shadow-2xs transition-all"
        />
      </div>

      {/* Filter Row */}
      <div className="flex flex-wrap items-center justify-between gap-3 text-xs sm:text-sm">
        <div className="flex flex-wrap items-center gap-2 sm:gap-3">
          {/* People Filter Dropdown */}
          <div className="relative">
            <select
              value={selectedPerson}
              onChange={(e) => setSelectedPerson(e.target.value)}
              className="appearance-none pl-3.5 pr-8 py-2 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] text-[#2d0a33] dark:text-[#e4d6eb] focus:outline-none cursor-pointer shadow-2xs font-medium"
            >
              <option value="todas">Todos</option>
              {peopleList.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-[#8f8298] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* Confidence Filter Dropdown */}
          <div className="relative">
            <select
              value={selectedConfidence}
              onChange={(e) => setSelectedConfidence(e.target.value)}
              className="appearance-none pl-3.5 pr-8 py-2 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] text-[#2d0a33] dark:text-[#e4d6eb] focus:outline-none cursor-pointer shadow-2xs font-medium"
            >
              <option value="todas">Toda confiança</option>
              <option value="alta">Alta (&gt; 85%)</option>
              <option value="media">Média (70% - 85%)</option>
              <option value="baixa">Baixa (&lt; 70%)</option>
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-[#8f8298] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>
        </div>

        {/* Sort Dropdown */}
        <div className="relative self-end sm:self-auto">
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as 'recentes' | 'antigos' | 'confianca')}
            className="appearance-none pl-3.5 pr-8 py-2 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] text-[#2d0a33] dark:text-[#e4d6eb] focus:outline-none cursor-pointer shadow-2xs font-medium"
          >
            <option value="recentes">Mais recentes</option>
            <option value="antigos">Mais antigos</option>
            <option value="confianca">Maior confiança</option>
          </select>
          <ChevronDown className="w-3.5 h-3.5 text-[#8f8298] absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none" />
        </div>
      </div>

      {/* Document Cards List */}
      <div className="space-y-3 pt-2">
        {filteredDocuments.length === 0 ? (
          <div className="py-16 text-center rounded-2xl border border-dashed border-[#ebe5ef] dark:border-[#2f1e39] bg-white/50 dark:bg-[#1a1120]/50">
            <FileText className="w-12 h-12 mx-auto text-[#a092a8] dark:text-[#5f5367] mb-2" />
            <p className="text-base font-semibold text-[#2d0a33] dark:text-white">
              Nenhum documento encontrado
            </p>
            <p className="text-xs text-[#8f8298] dark:text-[#7f7188] mt-1">
              Tente redefinir os filtros ou o termo de pesquisa.
            </p>
          </div>
        ) : (
          filteredDocuments.map((doc) => {
            const isFolhaPonto = category.id === 'folha_ponto'
            const openAudit = () =>
              setAuditDoc({ id: Number(doc.id), filename: doc.filename })

            return (
              <div
                key={doc.id}
                onClick={isFolhaPonto ? openAudit : undefined}
                onKeyDown={
                  isFolhaPonto
                    ? (e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          openAudit()
                        }
                      }
                    : undefined
                }
                role={isFolhaPonto ? 'button' : undefined}
                tabIndex={isFolhaPonto ? 0 : undefined}
                className={`group w-full rounded-2xl p-4 sm:p-5 border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] hover:border-[#c026d3]/40 dark:hover:border-[#c026d3]/50 transition-all flex items-start gap-4 shadow-2xs ${
                  isFolhaPonto
                    ? 'cursor-pointer hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c2c91]/40'
                    : ''
                }`}
              >
                {/* Document Icon Box */}
                <div className="w-10 h-10 rounded-xl bg-[#f5eff7] dark:bg-[#25152b] text-[#9333ea] dark:text-[#d67bf3] flex items-center justify-center shrink-0 mt-0.5">
                  <FileText className="w-5 h-5 stroke-[1.8]" />
                </div>

                {/* Document Content */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="text-base font-bold text-[#2d0a33] dark:text-[#f8f5fc] truncate">
                      {doc.filename}
                    </h3>

                    {/* Status de Auditoria (Integração com Goal 6 do Backend) */}
                    {isFolhaPonto && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation()
                          openAudit()
                        }}
                        title="Abrir auditoria da folha de ponto"
                        className="shrink-0 inline-flex items-center gap-2 h-9 px-3.5 rounded-xl text-xs font-semibold bg-[#f6effb] dark:bg-[#2b1738] text-[#6c2c91] dark:text-[#d8b4fe] border border-[#e3d2f0] dark:border-[#4c1d95] group-hover:bg-[#6c2c91] group-hover:text-white group-hover:border-[#6c2c91] hover:bg-[#6c2c91] hover:text-white hover:border-[#6c2c91] dark:group-hover:bg-[#7e22ce] dark:group-hover:text-white dark:group-hover:border-[#7e22ce] shadow-2xs transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#6c2c91]/40"
                      >
                        <ClipboardCheck className="w-4 h-4 shrink-0" />
                        <span>Ver auditoria</span>
                        <ChevronRight className="w-3.5 h-3.5 opacity-70" />
                      </button>
                    )}
                  </div>
                <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                  {doc.personName} · {doc.pages} página{doc.pages > 1 ? 's' : ''} · Processado em {doc.processedDate} · Confiança {Math.round(doc.confidence * 100)}%
                </p>

                {/* Metadata Badges / Tags */}
                <div className="flex flex-wrap items-center gap-2 mt-3">
                  {Object.entries(doc.campos || {})
                    .filter(([k, v]) => k !== 'nome' && k !== 'distingue_prestadora' && v)
                    .map(([key, value]) => (
                      <span
                        key={key}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]"
                      >
                        {campoLabels[key] || key}: {value}
                      </span>
                    ))}
                  {!doc.campos && doc.metadata.registrationNumber && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      Nº de registro: {doc.metadata.registrationNumber}
                    </span>
                  )}
                  {!doc.campos && doc.metadata.categoryType && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      Categoria: {doc.metadata.categoryType}
                    </span>
                  )}
                  {!doc.campos && doc.metadata.expirationDate && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      Validade: {doc.metadata.expirationDate}
                    </span>
                  )}
                  {!doc.campos && doc.metadata.cpfNumber && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      CPF: {doc.metadata.cpfNumber}
                    </span>
                  )}
                  {!doc.campos && doc.metadata.rgNumber && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      RG: {doc.metadata.rgNumber}
                    </span>
                  )}
                  {!doc.campos && doc.metadata.address && (
                    <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-[#f6f2f8] dark:bg-[#25172d] text-[#5b4d67] dark:text-[#c4b5cd] border border-[#ece4f1] dark:border-[#382343]">
                      Endereço: {doc.metadata.address}
                    </span>
                  )}
                </div>
              </div>
            </div>
            )
          })
        )}
      </div>

      {auditDoc && (
        <AuditoriaPontoModal
          documentoId={auditDoc.id}
          filename={auditDoc.filename}
          onClose={() => setAuditDoc(null)}
        />
      )}
    </div>
  )
}

export default CategoryPage
