import React, { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Download, FileText, X, ZoomIn, ZoomOut } from 'lucide-react'
import { downloadDocumento, fetchPageImage } from '../services/api'
import type { DetailedDocument } from '../types'

interface ThumbnailProps {
  loteId?: number
  page?: number
  alt: string
  onClick?: (e: React.MouseEvent) => void
}

export const DocumentThumbnail: React.FC<ThumbnailProps> = ({
  loteId,
  page,
  alt,
  onClick,
}) => {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (!loteId || !page) {
      setSrc(null)
      setFailed(true)
      return
    }
    const ctrl = new AbortController()
    let objectUrl: string | null = null
    setFailed(false)

    fetchPageImage(loteId, page, ctrl.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
      })
      .catch(() => {
        if (!ctrl.signal.aborted) {
          setFailed(true)
        }
      })

    return () => {
      ctrl.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [loteId, page])

  return (
    <button
      type="button"
      onClick={onClick}
      title="Visualizar documento"
      className="group/thumb relative w-14 h-[74px] rounded-xl overflow-hidden border border-[#e6dce9] dark:border-[#382343] bg-[#f5eff7] dark:bg-[#25152b] flex items-center justify-center shrink-0 cursor-pointer hover:border-[#9333ea] transition-all shadow-2xs"
    >
      {src && !failed ? (
        <img
          src={src}
          alt={alt}
          className="w-full h-full object-cover object-top"
        />
      ) : (
        <FileText className="w-5 h-5 text-[#9333ea] dark:text-[#d67bf3] stroke-[1.8]" />
      )}
      <span className="absolute inset-0 bg-[#2d0a33]/0 group-hover/thumb:bg-[#2d0a33]/40 transition-colors flex items-center justify-center">
        <ZoomIn className="w-4 h-4 text-white opacity-0 group-hover/thumb:opacity-100 transition-opacity" />
      </span>
    </button>
  )
}

interface PreviewModalProps {
  doc: DetailedDocument
  onClose: () => void
}

export const DocumentPreviewModal: React.FC<PreviewModalProps> = ({ doc, onClose }) => {
  const startPage = doc.startPage ?? 1
  const totalPages = Math.max(1, doc.pages || 1)
  const [pageOffset, setPageOffset] = useState(0)
  const [src, setSrc] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [downloading, setDownloading] = useState(false)
  const [zoom, setZoom] = useState(1)

  const currentPage = startPage + pageOffset

  useEffect(() => {
    setPageOffset(0)
    setZoom(1)
  }, [doc.id])

  useEffect(() => {
    setZoom(1)
  }, [pageOffset])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      else if (e.key === 'ArrowLeft' && pageOffset > 0) setPageOffset((p) => p - 1)
      else if (e.key === 'ArrowRight' && pageOffset < totalPages - 1) setPageOffset((p) => p + 1)
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [onClose, pageOffset, totalPages])

  useEffect(() => {
    if (!doc.loteId) {
      setLoading(false)
      setError(true)
      return
    }
    const ctrl = new AbortController()
    let objectUrl: string | null = null
    setLoading(true)
    setError(false)

    fetchPageImage(doc.loteId, currentPage, ctrl.signal)
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob)
        setSrc(objectUrl)
        setLoading(false)
      })
      .catch(() => {
        if (!ctrl.signal.aborted) {
          setError(true)
          setLoading(false)
        }
      })

    return () => {
      ctrl.abort()
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [doc.loteId, currentPage])

  const handleDownload = async () => {
    setDownloading(true)
    try {
      await downloadDocumento(Number(doc.id), doc.filename)
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-3 sm:p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Visualização de ${doc.filename}`}
    >
      <div
        className="w-full max-w-4xl max-h-[92vh] rounded-2xl bg-white dark:bg-[#1a1120] border border-[#ebe5ef] dark:border-[#2f1e39] shadow-2xl flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-4 sm:px-6 py-3.5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm sm:text-base font-bold text-[#2d0a33] dark:text-[#f8f5fc] truncate">
              {doc.filename}
            </h2>
            <p className="text-xs text-[#6e6378] dark:text-[#a093a8] truncate">
              {doc.personName} · Página {pageOffset + 1} de {totalPages}
              {doc.originalFilename && doc.originalFilename !== doc.filename
                ? ` · Original: ${doc.originalFilename}`
                : ''}
            </p>
          </div>

          <div className="shrink-0 flex items-center gap-2">
            {/* Controles de Lupa / Zoom */}
            <div className="hidden sm:inline-flex items-center rounded-xl border border-[#e6dce9] dark:border-[#382343] bg-[#f6f2f8] dark:bg-[#25172d] p-0.5">
              <button
                type="button"
                onClick={() => setZoom((z) => Math.max(1, Number((z - 0.5).toFixed(1))))}
                disabled={zoom <= 1}
                title="Diminuir zoom"
                aria-label="Diminuir zoom"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[#4b3e56] dark:text-[#d5c7df] hover:bg-white dark:hover:bg-[#32203d] disabled:opacity-40 transition-colors cursor-pointer"
              >
                <ZoomOut className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => setZoom(1)}
                title="Resetar zoom (100%)"
                className="px-2 h-8 text-[11px] font-semibold text-[#4b3e56] dark:text-[#d5c7df] hover:bg-white dark:hover:bg-[#32203d] rounded-lg transition-colors cursor-pointer"
              >
                {Math.round(zoom * 100)}%
              </button>
              <button
                type="button"
                onClick={() => setZoom((z) => Math.min(2.5, Number((z + 0.5).toFixed(1))))}
                disabled={zoom >= 2.5}
                title="Aumentar zoom (lupa)"
                aria-label="Aumentar zoom"
                className="w-8 h-8 rounded-lg flex items-center justify-center text-[#4b3e56] dark:text-[#d5c7df] hover:bg-white dark:hover:bg-[#32203d] disabled:opacity-40 transition-colors cursor-pointer"
              >
                <ZoomIn className="w-3.5 h-3.5" />
              </button>
            </div>

            <button
              type="button"
              onClick={handleDownload}
              disabled={downloading}
              className="inline-flex items-center gap-1.5 h-9 px-3 rounded-xl text-xs font-semibold bg-[#6c2c91] text-white hover:bg-[#582277] transition-colors cursor-pointer disabled:opacity-50"
            >
              <Download className="w-3.5 h-3.5" />
              <span>{downloading ? 'Baixando...' : 'Baixar PDF'}</span>
            </button>
            <button
              type="button"
              onClick={onClose}
              aria-label="Fechar visualização"
              className="w-9 h-9 rounded-xl flex items-center justify-center text-[#6e6378] hover:text-[#2d0a33] hover:bg-[#f5eff7] dark:text-[#a093a8] dark:hover:text-white dark:hover:bg-[#2a1934] transition-colors cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Image Area */}
        <div
          className={`flex-1 overflow-auto bg-[#f6f2f8] dark:bg-[#120b17] p-4 flex min-h-[360px] ${
            zoom > 1 ? 'items-start justify-start' : 'items-center justify-center'
          }`}
        >
          {loading ? (
            <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">Carregando visualização...</p>
          ) : error || !src ? (
            <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
              Visualização indisponível para esta página.
            </p>
          ) : (
            <img
              src={src}
              alt={`${doc.filename} - página ${pageOffset + 1}`}
              onClick={() => setZoom((z) => (z > 1 ? 1 : 2))}
              title={zoom > 1 ? 'Clique para reduzir' : 'Clique para ampliar com a lupa'}
              style={zoom > 1 ? { width: `${zoom * 100}%`, maxWidth: 'none' } : undefined}
              className={`rounded-lg shadow-md border border-[#e6dce9] dark:border-[#2f1e39] bg-white transition-all ${
                zoom > 1
                  ? 'cursor-zoom-out'
                  : 'max-w-full max-h-[70vh] cursor-zoom-in'
              }`}
            />
          )}
        </div>

        {/* Pagination Footer */}
        {totalPages > 1 && (
          <div className="px-4 py-2.5 border-t border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={() => setPageOffset((p) => Math.max(0, p - 1))}
              disabled={pageOffset === 0}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-[#e1d9e6] dark:border-[#35223e] text-[#2d0a33] dark:text-[#eae0ee] hover:bg-[#f5eff7] dark:hover:bg-[#25162a] disabled:opacity-40 cursor-pointer"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              Anterior
            </button>
            <span className="text-xs font-medium text-[#6e6378] dark:text-[#a093a8]">
              {pageOffset + 1} / {totalPages}
            </span>
            <button
              type="button"
              onClick={() => setPageOffset((p) => Math.min(totalPages - 1, p + 1))}
              disabled={pageOffset >= totalPages - 1}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium border border-[#e1d9e6] dark:border-[#35223e] text-[#2d0a33] dark:text-[#eae0ee] hover:bg-[#f5eff7] dark:hover:bg-[#25162a] disabled:opacity-40 cursor-pointer"
            >
              Próxima
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

