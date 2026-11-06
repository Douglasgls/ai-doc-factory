import React, { useState, useEffect, useCallback, useMemo } from 'react'
import { Check, X, Plus, ExternalLink, Loader2 } from 'lucide-react'
import type { ReviewPendingDocument } from '../types'

export interface CategoryOption {
  slug: string
  name: string
}

interface ManualReviewPageProps {
  documents: ReviewPendingDocument[]
  onBack: () => void
  onApprove: (
    docId: string,
    finalCategory: string,
    personName: string,
    updatedFields?: Record<string, string | null>
  ) => void | Promise<void>
  availableCategories: (string | CategoryOption)[]
}

interface DetailPanelProps {
  doc: ReviewPendingDocument
  categories: CategoryOption[]
  onConfirm: (
    docId: string,
    category: string,
    name: string,
    fields?: Record<string, string | null>
  ) => void | Promise<void>
  onAcceptSuggestion: (doc: ReviewPendingDocument) => void | Promise<void>
}

const ReviewDetailPanel: React.FC<DetailPanelProps> = ({
  doc,
  categories,
  onConfirm,
  onAcceptSuggestion,
}) => {
  const [selectedCategory, setSelectedCategory] = useState(doc.suggestedType)
  const [personName, setPersonName] = useState(doc.personName)
  const [extractedFields, setExtractedFields] = useState(doc.extractedFields)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const handleRemoveField = (index: number) => {
    setExtractedFields((prev) => prev.filter((_, i) => i !== index))
  }

  const handleAddField = () => {
    setExtractedFields((prev) => [...prev, { key: 'campo', value: '' }])
  }

  const suggestedCategoryName = useMemo(() => {
    const found = categories.find(
      (c) => c.slug.toLowerCase() === doc.suggestedType.toLowerCase()
    )
    return found ? found.name : doc.suggestedType
  }, [categories, doc.suggestedType])

  const handleConfirmClick = async () => {
    setIsSubmitting(true)
    setActionError(null)
    try {
      const fieldsMap: Record<string, string | null> = {}
      for (const field of extractedFields) {
        const sanitizedKey = field.key
          .trim()
          .toLowerCase()
          .replace(/[^a-z0-9_]/g, '_')
          .slice(0, 40)
        if (sanitizedKey) {
          const val = field.value.trim()
          fieldsMap[sanitizedKey] = val ? val.slice(0, 500) : null
        }
      }
      if (personName.trim()) {
        fieldsMap['nome'] = personName.trim().slice(0, 500)
      }
      await onConfirm(doc.id, selectedCategory, personName, fieldsMap)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao confirmar documento')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleAcceptClick = async () => {
    setIsSubmitting(true)
    setActionError(null)
    try {
      await onAcceptSuggestion(doc)
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Erro ao aceitar sugestão')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="lg:col-span-7 rounded-2xl p-6 sm:p-7 border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-xs space-y-6">
      {/* Document Header */}
      <div>
        <h3 className="text-lg font-bold text-[#2d0a33] dark:text-[#f8f5fc]">
          {doc.filename}
        </h3>
        <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#a093a8] mt-0.5">
          Processado em {doc.processedDate} · {doc.timeAgo} · {doc.pages} página{doc.pages > 1 ? 's' : ''}
        </p>
      </div>

      {/* Document Image Preview (quando disponível na API) */}
      {doc.imagemUrl && (
        <div className="rounded-xl overflow-hidden border border-[#ebe5ef] dark:border-[#2f1e39] bg-[#f8f5fa] dark:bg-[#150c18] p-3 space-y-2">
          <div className="flex items-center justify-between text-xs font-semibold text-[#6e6378] dark:text-[#a093a8]">
            <span>Visualização da página ({doc.pages} pág.)</span>
            <a
              href={doc.imagemUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#9333ea] dark:text-[#d67bf3] hover:underline flex items-center gap-1 cursor-pointer"
            >
              <span>Abrir original</span>
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
          <div className="flex justify-center bg-black/5 dark:bg-black/30 rounded-lg p-2 max-h-72 overflow-hidden">
            <img
              src={doc.imagemUrl}
              alt={doc.filename}
              className="max-h-64 object-contain rounded shadow-xs"
              onError={(e) => {
                const container = e.currentTarget.parentElement?.parentElement
                if (container) container.style.display = 'none'
              }}
            />
          </div>
        </div>
      )}

      {/* Alert / Diagnosis Box */}
      <div className="p-4 rounded-xl bg-[#f8f5fa] dark:bg-[#201326] border border-[#ece4f1] dark:border-[#382240] text-xs sm:text-sm space-y-1">
        <p className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">
          {doc.issueDescription}
        </p>
        <p className="text-[#6e6378] dark:text-[#a093a8]">
          Tipo sugerido pela IA: <strong className="font-bold text-[#9333ea] dark:text-[#d67bf3]">{suggestedCategoryName}</strong> · confiança {Math.round(doc.suggestedConfidence * 100)}%
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
              <div className="px-3.5 py-2 bg-[#f8f5fa] dark:bg-[#201224] border-r border-[#ebe5ef] dark:border-[#2f1e39] text-xs font-semibold text-[#6e6378] dark:text-[#a093a8] min-w-[70px]">
                {field.key}
              </div>
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
            {categories.map((cat) => (
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

      {/* Error Message */}
      {actionError && (
        <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900/50 text-xs font-medium text-red-600 dark:text-red-400">
          {actionError}
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex flex-wrap items-center gap-3 pt-3">
        <button
          type="button"
          disabled={isSubmitting}
          onClick={handleConfirmClick}
          className="px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] disabled:opacity-50 flex items-center gap-2 shadow-2xs transition-all cursor-pointer"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Check className="w-4 h-4 stroke-[2.5]" />
          )}
          <span>Confirmar classificação</span>
        </button>

        <button
          type="button"
          disabled={isSubmitting}
          onClick={handleAcceptClick}
          className="px-5 py-2.5 rounded-xl text-xs sm:text-sm font-semibold border border-[#d88cf5] dark:border-[#c026d3] text-[#7c1782] dark:text-[#f38df9] hover:bg-[#f6ebfa] dark:hover:bg-[#281530] disabled:opacity-50 flex items-center gap-2 transition-all cursor-pointer"
        >
          {isSubmitting ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : null}
          <span>Aceitar sugestão ({suggestedCategoryName})</span>
        </button>
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
  const [selectedDocId, setSelectedDocId] = useState<string>(documents[0]?.id || '')
  const [selectedCheckboxes, setSelectedCheckboxes] = useState<Record<string, boolean>>({})
  const [bulkCategory, setBulkCategory] = useState<string>('')

  const normalizedCategories: CategoryOption[] = useMemo(() => {
    return availableCategories.map((c) =>
      typeof c === 'string'
        ? { slug: c.toLowerCase().replace(/\s+/g, '_'), name: c }
        : c
    )
  }, [availableCategories])

  // Selected document
  const currentDoc =
    documents.find((d) => d.id === selectedDocId) || documents[0]

  const handleAcceptSuggestion = useCallback(
    async (doc: ReviewPendingDocument) => {
      await onApprove(doc.id, doc.suggestedType, doc.personName)
      const remaining = documents.filter((d) => d.id !== doc.id)
      if (remaining.length > 0) {
        setSelectedDocId(remaining[0].id)
      }
    },
    [documents, onApprove]
  )

  // Keyboard navigation & shortcuts (↑ / ↓ to navigate, 'A' to accept suggestion)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'SELECT', 'TEXTAREA'].includes((e.target as HTMLElement)?.tagName)) {
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
      } else if (e.key.toLowerCase() === 'a') {
        e.preventDefault()
        if (currentDoc) {
          handleAcceptSuggestion(currentDoc)
        }
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [documents, currentDoc, handleAcceptSuggestion])

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

  const handleConfirmClassification = async (
    docId: string,
    category: string,
    name: string,
    fields?: Record<string, string | null>
  ) => {
    await onApprove(docId, category, name, fields)
    const remaining = documents.filter((d) => d.id !== docId)
    if (remaining.length > 0) {
      setSelectedDocId(remaining[0].id)
    }
  }

  // Handle bulk action approval
  const handleApplyBulk = async () => {
    if (!bulkCategory) return
    const idsToProcess = Object.keys(selectedCheckboxes).filter((id) => selectedCheckboxes[id])
    for (const id of idsToProcess) {
      const doc = documents.find((d) => d.id === id)
      if (doc) {
        await onApprove(doc.id, bulkCategory, doc.personName)
      }
    }
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
                    {normalizedCategories.map((cat) => (
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
              categories={normalizedCategories}
              onConfirm={handleConfirmClassification}
              onAcceptSuggestion={handleAcceptSuggestion}
            />
          )}
        </div>
      )}
    </div>
  )
}

export default ManualReviewPage
