import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { Check, X, Plus } from 'lucide-react'
import type { ReviewPendingDocument } from '../types'
import { fetchPageImage } from '../services/api'

export interface CategoryOption {
  slug: string
  name: string
}

export const OFFICIAL_CATEGORY_OPTIONS: CategoryOption[] = [
  { slug: 'aso', name: 'ASO (Atestado de Saúde Ocupacional)' },
  { slug: 'folha_pagamento', name: 'Folha de pagamento' },
  { slug: 'folha_ponto', name: 'Folha de ponto' },
  { slug: 'holerite', name: 'Holerite' },
  { slug: 'recibo_ferias', name: 'Recibo de férias' },
  { slug: 'atestado_medico', name: 'Atestado médico' },
  { slug: 'contrato_trabalho', name: 'Contrato de trabalho' },
]

const VALID_CATEGORY_SLUGS = new Set(OFFICIAL_CATEGORY_OPTIONS.map((c) => c.slug))

interface ManualReviewPageProps {
  documents: ReviewPendingDocument[]
  onBack: () => void
  onApprove: (
    docId: string,
    finalCategorySlug: string,
    personName: string,
    updatedFields?: { key: string; value: string }[],
    initialCampos?: Record<string, string>
  ) => void
  availableCategories: CategoryOption[]
}

interface DetailPanelProps {
  doc: ReviewPendingDocument
  availableCategories: CategoryOption[]
  onConfirm: (
    docId: string,
    categorySlug: string,
    name: string,
    updatedFields: { key: string; value: string }[],
    initialCampos?: Record<string, string>
  ) => void
}

const ReviewDetailPanel: React.FC<DetailPanelProps> = ({
  doc,
  availableCategories,
  onConfirm,
}) => {
  const isValidSuggestion = VALID_CATEGORY_SLUGS.has(doc.suggestedType)
  const [selectedCategory, setSelectedCategory] = useState(
    isValidSuggestion
      ? doc.suggestedType
      : availableCategories[0]?.slug || OFFICIAL_CATEGORY_OPTIONS[0].slug
  )
  const [personName, setPersonName] = useState(doc.personName)
  const [extractedFields, setExtractedFields] = useState(doc.extractedFields)
  const [currentPage, setCurrentPage] = useState(0)

  useEffect(() => {
    const valid = VALID_CATEGORY_SLUGS.has(doc.suggestedType)
      ? doc.suggestedType
      : availableCategories[0]?.slug || OFFICIAL_CATEGORY_OPTIONS[0].slug
    setSelectedCategory((prev) => (VALID_CATEGORY_SLUGS.has(prev) ? prev : valid))
  }, [doc.id, doc.suggestedType, availableCategories])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        ['INPUT', 'SELECT', 'TEXTAREA'].includes(
          (e.target as HTMLElement)?.tagName
        )
      ) {
        return
      }
      if (e.key.toLowerCase() === 'a') {
        e.preventDefault()
        onConfirm(
          doc.id,
          selectedCategory,
          personName,
          extractedFields,
          doc.initialCampos
        )
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [doc.id, doc.initialCampos, selectedCategory, personName, extractedFields, onConfirm])

  const handleRemoveField = (index: number) => {
    setExtractedFields((prev) => prev.filter((_, i) => i !== index))
  }

  const handleAddField = () => {
    setExtractedFields((prev) => [...prev, { key: 'novo_campo', value: '' }])
  }

  // <img src> não envia Authorization: baixa a imagem autenticada e usa um object URL (revogado ao trocar/desmontar)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [imageFailed, setImageFailed] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    let objectUrl: string | null = null
    setImageUrl(null)
    setImageFailed(false)
    fetchPageImage(doc.loteId, doc.startPage + currentPage, controller.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setImageUrl(objectUrl)
      })
      .catch(() => {
        if (!controller.signal.aborted) setImageFailed(true)
      })
    return () => {
      controller.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [doc.loteId, doc.startPage, currentPage])

  const suggestedLabel =
    doc.suggestedTypeLabel ||
    availableCategories.find((c) => c.slug === doc.suggestedType)?.name ||
    doc.suggestedType

  return (
    <div className="lg:col-span-7 space-y-6">
      <div className="rounded-2xl p-6 sm:p-7 border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-xs space-y-6">
        {/* Document Header */}
        <div className="flex justify-between items-start">
          <div>
            <h3 className="text-lg font-bold text-[#2d0a33] dark:text-[#f8f5fc]">
              {doc.filename}
            </h3>
            <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#a093a8] mt-0.5">
              Processado em {doc.processedDate} · {doc.timeAgo} · {doc.pages} página{doc.pages > 1 ? 's' : ''}
            </p>
          </div>
        </div>

        {/* Visualizer (Imagem real da página no backend) */}
        <div className="relative aspect-[3/4] w-full bg-[#f3f0f5] dark:bg-[#150c18] rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] overflow-hidden group shadow-inner">
          {imageUrl ? (
            <img
              src={imageUrl}
              alt="Documento"
              className="w-full h-full object-contain p-4"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-sm text-[#6e6378] dark:text-[#a093a8]">
              {imageFailed ? 'Imagem indisponível' : 'Carregando imagem...'}
            </div>
          )}

          {doc.pages > 1 && (
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 px-3 py-1.5 rounded-full bg-black/50 backdrop-blur-md text-white text-[10px] font-bold">
              <button
                onClick={() => setCurrentPage((prev) => Math.max(0, prev - 1))}
                disabled={currentPage === 0}
                className="hover:text-[#d67bf3] disabled:opacity-30 transition-colors"
              >
                Anterior
              </button>
              <span>
                Página {currentPage + 1} de {doc.pages}
              </span>
              <button
                onClick={() =>
                  setCurrentPage((prev) => Math.min(doc.pages - 1, prev + 1))
                }
                disabled={currentPage === doc.pages - 1}
                className="hover:text-[#d67bf3] disabled:opacity-30 transition-colors"
              >
                Próxima
              </button>
            </div>
          )}
        </div>

        {/* Alert / Diagnosis Box */}
        <div className="p-4 rounded-xl bg-[#f8f5fa] dark:bg-[#201326] border border-[#ece4f1] dark:border-[#382240] text-xs sm:text-sm space-y-1">
          <p className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
            {doc.issueDescription}
          </p>
          <p className="text-[#6e6378] dark:text-[#a093a8]">
            Tipo sugerido pela IA:{' '}
            <strong className="font-bold text-[#9333ea] dark:text-[#d67bf3]">
              {suggestedLabel}
            </strong>{' '}
            · confiança {Math.round(doc.suggestedConfidence * 100)}%
          </p>
        </div>

        {/* Informações Extraídas Section */}
        <div className="space-y-3">
          <h4 className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc]">
            Informações extraídas
          </h4>

          <div className="space-y-2">
            {extractedFields.map((field, idx) => (
              <div
                key={idx}
                className="flex items-center rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] overflow-hidden bg-white dark:bg-[#150c18]"
              >
                <input
                  type="text"
                  value={field.key}
                  onChange={(e) => {
                    const keyVal = e.target.value
                    setExtractedFields((prev) =>
                      prev.map((f, i) => (i === idx ? { ...f, key: keyVal } : f))
                    )
                  }}
                  aria-label="Nome do campo"
                  className="px-3.5 py-2 bg-[#f8f5fa] dark:bg-[#201224] border-r border-[#ebe5ef] dark:border-[#2f1e39] text-xs font-semibold text-[#6e6378] dark:text-[#a093a8] w-32 focus:outline-none"
                />
                <input
                  type="text"
                  value={field.value}
                  onChange={(e) => {
                    const val = e.target.value
                    setExtractedFields((prev) =>
                      prev.map((f, i) => (i === idx ? { ...f, value: val } : f))
                    )
                    if (field.key.toLowerCase() === 'nome') {
                      setPersonName(val)
                    }
                  }}
                  className="flex-1 px-3 py-2 text-xs sm:text-sm text-[#2d0a33] dark:text-white bg-transparent focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => handleRemoveField(idx)}
                  className="p-2 text-[#8f8298] hover:text-[#e11d48] transition-colors cursor-pointer"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>

          <button
            type="button"
            onClick={handleAddField}
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#9333ea] dark:text-[#d67bf3] hover:underline cursor-pointer pt-1"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Adicionar campo</span>
          </button>
        </div>

        {/* Classification Inputs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div>
            <label className="block text-xs font-semibold text-[#6e6378] dark:text-[#a093a8] mb-1.5">
              Tipo documental
            </label>
            <select
              value={selectedCategory}
              onChange={(e) => setSelectedCategory(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#150c18] text-[#2d0a33] dark:text-white text-xs sm:text-sm focus:outline-none focus:ring-1 focus:ring-[#9333ea] cursor-pointer"
            >
              {availableCategories.map((cat) => (
                <option key={cat.slug} value={cat.slug}>
                  {cat.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#6e6378] dark:text-[#a093a8] mb-1.5">
              Nome da pessoa
            </label>
            <input
              type="text"
              value={personName}
              onChange={(e) => setPersonName(e.target.value)}
              placeholder="Nome completo"
              className="w-full px-3.5 py-2.5 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#150c18] text-[#2d0a33] dark:text-white text-xs sm:text-sm focus:outline-none focus:ring-1 focus:ring-[#9333ea]"
            />
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex flex-wrap items-center gap-3 pt-3">
          <button
            type="button"
            onClick={() =>
              onConfirm(
                doc.id,
                selectedCategory,
                personName,
                extractedFields,
                doc.initialCampos
              )
            }
            className="px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] flex items-center gap-2 shadow-2xs transition-all cursor-pointer"
          >
            <Check className="w-4 h-4 stroke-[2.5]" />
            <span>Confirmar classificação</span>
          </button>

          {isValidSuggestion && selectedCategory === doc.suggestedType && (
            <button
              type="button"
              onClick={() =>
                onConfirm(
                  doc.id,
                  selectedCategory,
                  personName,
                  extractedFields,
                  doc.initialCampos
                )
              }
              className="px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold border border-[#d88cf5] dark:border-[#c026d3] text-[#7c1782] dark:text-[#f38df9] hover:bg-[#f6ebfa] dark:hover:bg-[#281530] flex items-center gap-2 transition-all cursor-pointer"
            >
              <span>Aceitar sugestão ({suggestedLabel})</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

const ManualReviewPage: React.FC<ManualReviewPageProps> = ({
  documents,
  onBack,
  onApprove,
  availableCategories,
}) => {
  const [selectedDocId, setSelectedDocId] = useState<string>(
    documents[0]?.id || ''
  )
  const [selectedCheckboxes, setSelectedCheckboxes] = useState<
    Record<string, boolean>
  >({})
  const [bulkCategory, setBulkCategory] = useState<string>('')

  const categoryOptions = useMemo(() => {
    const valid = availableCategories.filter((c) => VALID_CATEGORY_SLUGS.has(c.slug))
    return valid.length > 0 ? valid : OFFICIAL_CATEGORY_OPTIONS
  }, [availableCategories])

  // Selected document
  const currentDoc =
    documents.find((d) => d.id === selectedDocId) || documents[0]

  // Keyboard navigation (↑ / ↓ to navigate)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        ['INPUT', 'SELECT', 'TEXTAREA'].includes(
          (e.target as HTMLElement)?.tagName
        )
      ) {
        return
      }

      const currentIndex = documents.findIndex((d) => d.id === currentDoc?.id)

      if (e.key === 'ArrowDown') {
        e.preventDefault()
        if (currentIndex < documents.length - 1) {
          setSelectedDocId(documents[currentIndex + 1].id)
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        if (currentIndex > 0) {
          setSelectedDocId(documents[currentIndex - 1].id)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [documents, currentDoc])

  const handleConfirmClassification = useCallback(
    (
      docId: string,
      categorySlug: string,
      name: string,
      updatedFields: { key: string; value: string }[],
      initialCampos?: Record<string, string>
    ) => {
      onApprove(docId, categorySlug, name, updatedFields, initialCampos)
      const remaining = documents.filter((d) => d.id !== docId)
      if (remaining.length > 0) {
        setSelectedDocId(remaining[0].id)
      }
    },
    [documents, onApprove]
  )

  const handleSelectAll = (checked: boolean) => {
    const updated: Record<string, boolean> = {}
    documents.forEach((d) => {
      updated[d.id] = checked
    })
    setSelectedCheckboxes(updated)
  }

  const toggleSelectDoc = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setSelectedCheckboxes((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  // Handle bulk action approval
  const handleApplyBulk = () => {
    if (!bulkCategory) return
    const idsToProcess = Object.keys(selectedCheckboxes).filter(
      (id) => selectedCheckboxes[id]
    )
    idsToProcess.forEach((id) => {
      const doc = documents.find((d) => d.id === id)
      if (doc) {
        onApprove(
          doc.id,
          bulkCategory,
          doc.personName,
          doc.extractedFields,
          doc.initialCampos
        )
      }
    })
    setSelectedCheckboxes({})
    setBulkCategory('')
  }

  const allSelected =
    documents.length > 0 && documents.every((d) => selectedCheckboxes[d.id])

  const selectedCount = Object.values(selectedCheckboxes).filter(Boolean).length

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
          Revisão manual
        </span>
      </nav>

      {/* Header Title */}
      <div>
        <h1 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#f8f5fc]">
          Revisão manual
        </h1>
      </div>

      {documents.length === 0 ? (
        <div className="py-20 text-center rounded-2xl border border-dashed border-[#ebe5ef] dark:border-[#2f1e39] bg-white/50 dark:bg-[#1a1120]/50">
          <div className="w-14 h-14 mx-auto rounded-full bg-emerald-100 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 flex items-center justify-center mb-3">
            <Check className="w-7 h-7" />
          </div>
          <h3 className="text-lg font-bold text-[#2d0a33] dark:text-white">
            Nenhum documento pendente de revisão!
          </h3>
          <p className="text-sm text-[#6e6378] dark:text-[#a093a8] mt-1">
            Todos os documentos foram verificados e aprovados com sucesso.
          </p>
          <button
            onClick={onBack}
            className="mt-5 px-5 py-2 rounded-xl text-sm font-medium text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] transition-all cursor-pointer"
          >
            Voltar para Documentos
          </button>
        </div>
      ) : (
        /* Main 2-Column Review Interface */
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
          {/* Left Column: Documents Queue */}
          <div className="lg:col-span-5 space-y-3">
            {/* Bulk Action Header / Select All Checkbox */}
            {selectedCount > 0 ? (
              <div className="w-full p-4 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-xs space-y-3 animate-in fade-in duration-150">
                <div className="text-sm font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
                  {selectedCount} selecionado(s)
                </div>

                <div className="relative">
                  <select
                    value={bulkCategory}
                    onChange={(e) => setBulkCategory(e.target.value)}
                    className="w-full px-3.5 py-2 rounded-xl border border-[#c026d3] text-sm text-[#2d0a33] dark:text-white bg-white dark:bg-[#150c18] focus:outline-none focus:ring-1 focus:ring-[#c026d3] cursor-pointer"
                  >
                    <option value="">Classificar como...</option>
                    {categoryOptions.map((cat) => (
                      <option key={cat.slug} value={cat.slug}>
                        {cat.name}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    disabled={!bulkCategory}
                    onClick={handleApplyBulk}
                    className="px-4 py-1.5 rounded-lg text-xs font-semibold text-white bg-[#9b88a1] hover:bg-[#85718b] dark:bg-[#684f72] dark:hover:bg-[#7b5f87] disabled:opacity-50 transition-colors cursor-pointer"
                  >
                    Aplicar
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedCheckboxes({})}
                    className="text-xs font-medium text-[#7a6b85] dark:text-[#9f91a6] hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer"
                  >
                    Limpar
                  </button>
                </div>
              </div>
            ) : (
              <label className="flex items-center gap-2.5 text-xs sm:text-sm font-medium text-[#6e6378] dark:text-[#a093a8] px-1 cursor-pointer select-none">
                <div
                  onClick={() => handleSelectAll(!allSelected)}
                  className={`w-4 h-4 rounded flex items-center justify-center transition-colors cursor-pointer ${
                    allSelected
                      ? 'bg-[#3e0b48] dark:bg-[#9917a2] text-white'
                      : 'border border-[#b6abbd] dark:border-[#422c4d] bg-white dark:bg-[#1a1120]'
                  }`}
                >
                  {allSelected && <Check className="w-3 h-3 stroke-[3]" />}
                </div>
                <span>Selecionar todos</span>
              </label>
            )}

            {/* Document Queue Cards */}
            <div className="space-y-2.5">
              {documents.map((doc) => {
                const isSelected = doc.id === currentDoc?.id
                const isChecked = !!selectedCheckboxes[doc.id]

                return (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDocId(doc.id)}
                    className={`w-full p-4 rounded-xl transition-all cursor-pointer flex items-start gap-3 select-none relative overflow-hidden ${
                      isSelected
                        ? 'border-y border-r border-[#ebe5ef] dark:border-[#2f1e39] border-l-[4px] border-l-[#86198f] dark:border-l-[#c026d3] bg-white dark:bg-[#1a1120] shadow-xs'
                        : 'border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] hover:border-[#c026d3]/40'
                    }`}
                  >
                    {/* Custom Checkbox */}
                    <div
                      onClick={(e) => toggleSelectDoc(doc.id, e)}
                      className={`w-4 h-4 rounded flex items-center justify-center shrink-0 mt-0.5 transition-colors cursor-pointer ${
                        isChecked
                          ? 'bg-[#3e0b48] dark:bg-[#9917a2] text-white'
                          : 'border border-[#b6abbd] dark:border-[#422c4d] bg-white dark:bg-[#1a1120]'
                      }`}
                    >
                      {isChecked && <Check className="w-3 h-3 stroke-[3]" />}
                    </div>

                    <div className="min-w-0 flex-1">
                      <h4 className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc] truncate">
                        {doc.filename}
                      </h4>
                      <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                        {doc.issueLabel} · {doc.timeAgo.toLowerCase()}
                      </p>
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Keyboard Shortcuts Hint */}
            <div className="flex items-center gap-1.5 text-xs text-[#8f8298] dark:text-[#7f7188] pt-2 px-1">
              <kbd className="px-1.5 py-0.5 rounded border border-[#d5ccd9] dark:border-[#422c4d] bg-white dark:bg-[#1f1325] text-[11px] font-mono leading-none">
                ↑
              </kbd>
              <kbd className="px-1.5 py-0.5 rounded border border-[#d5ccd9] dark:border-[#422c4d] bg-white dark:bg-[#1f1325] text-[11px] font-mono leading-none">
                ↓
              </kbd>
              <span>navegar</span>
              <span>·</span>
              <kbd className="px-1.5 py-0.5 rounded border border-[#d5ccd9] dark:border-[#422c4d] bg-white dark:bg-[#1f1325] text-[11px] font-mono leading-none">
                A
              </kbd>
              <span>aceitar sugestão</span>
            </div>
          </div>

          {/* Right Column: Active Document Analysis & Action Panel */}
          {currentDoc && (
            <ReviewDetailPanel
              key={currentDoc.id}
              doc={currentDoc}
              availableCategories={categoryOptions}
              onConfirm={handleConfirmClassification}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default ManualReviewPage
