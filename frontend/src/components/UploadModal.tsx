import React, { useEffect, useState } from 'react'
import { X, UploadCloud, File, Loader2, AlertCircle, Trash2 } from 'lucide-react'
import { apiService, type Contrato } from '../services/api'
import { contratoLabel, contratoUtilizavel } from '../utils/contratos'
import { ehEmpresaPropria } from '../utils/permissoes'

interface UploadModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccessUpload: (filename: string, loteId: number) => void
  onUploadFiles?: (files: File[], contratoId: number | null) => void
  /** Prestador precisa escolher um contrato; plataforma pode enviar sem contrato. */
  contratoObrigatorio?: boolean
}

/** Mesmo limite do backend (UPLOAD_MAX_MB, padrão 50). O limite de páginas só o backend confere. */
const MAX_UPLOAD_MB = 50
const MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

const ACCEPTED_EXTENSIONS = ['.pdf', '.jpg', '.jpeg', '.png', '.tif', '.tiff']

function isValidUploadFile(file: File): boolean {
  const lower = file.name.toLowerCase()
  return ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

export const UploadModal: React.FC<UploadModalProps> = ({
  isOpen,
  onClose,
  onSuccessUpload,
  onUploadFiles,
  contratoObrigatorio = false,
}) => {
  const [files, setFiles] = useState<File[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<{ current: number; total: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [contratoId, setContratoId] = useState<string>('')
  const [contratosErro, setContratosErro] = useState<string | null>(null)
  const [contratosCarregados, setContratosCarregados] = useState(false)

  useEffect(() => {
    if (!isOpen) return
    let cancelado = false
    apiService
      .getContratos()
      .then((lista) => {
        if (cancelado) return
        setContratosErro(null)
        const utilizaveis = lista.filter(contratoUtilizavel)
        setContratos(utilizaveis)
        setContratosCarregados(true)
        // Mantém a escolha se ainda vale; prestador com um único contrato ativo já vem com ele selecionado.
        setContratoId((atual) => {
          if (atual !== '' && utilizaveis.some((c) => String(c.id) === atual)) return atual
          if (contratoObrigatorio && utilizaveis.length === 1) return String(utilizaveis[0].id)
          return ''
        })
      })
      .catch((err) => {
        if (!cancelado) setContratosErro(err instanceof Error ? err.message : 'Erro ao listar contratos')
      })
    return () => {
      cancelado = true
    }
  }, [isOpen, contratoObrigatorio])

  if (!isOpen) return null

  const contratoSelecionado = contratoId === '' ? null : Number(contratoId)
  const contratoEscolhido = contratos.find((c) => c.id === contratoSelecionado)
  const contratoSelecionadoTexto = contratoEscolhido ? contratoLabel(contratoEscolhido) : ''
  const faltaContrato = contratoObrigatorio && contratoSelecionado === null
  // Empresa solo (um único contrato, próprio): o contrato já vem selecionado e o seletor some.
  const empresaPropria =
    contratoObrigatorio && contratos.length === 1 && ehEmpresaPropria({ nivel: 'prestador' }, contratos)

  const addFiles = (incomingFiles: FileList | File[]) => {
    const list = Array.from(incomingFiles)
    if (list.length === 0) return

    const invalid = list.filter((f) => !isValidUploadFile(f))
    const formatoOk = list.filter((f) => isValidUploadFile(f))
    const grandes = formatoOk.filter((f) => f.size > MAX_UPLOAD_BYTES)
    const valid = formatoOk.filter((f) => f.size <= MAX_UPLOAD_BYTES)

    if (invalid.length > 0) {
      setError(
        `Formato não suportado (${invalid.map((f) => f.name).join(', ')}). Use PDF, JPEG, PNG ou TIFF.`
      )
    } else if (grandes.length > 0) {
      setError(`Arquivo maior que ${MAX_UPLOAD_MB} MB (${grandes.map((f) => f.name).join(', ')}).`)
    } else {
      setError(null)
    }

    if (valid.length > 0) {
      setFiles((prev) => {
        const existingKeys = new Set(prev.map((f) => `${f.name}-${f.size}-${f.lastModified}`))
        const uniqueNew = valid.filter(
          (f) => !existingKeys.has(`${f.name}-${f.size}-${f.lastModified}`)
        )
        return [...prev, ...uniqueNew]
      })
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addFiles(e.target.files)
      e.target.value = ''
    }
  }

  const handleDragOver = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault()
    e.stopPropagation()
    if (!isUploading) {
      setIsDragging(true)
    }
  }

  const handleDragLeave = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent<HTMLElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (isUploading) return

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addFiles(e.dataTransfer.files)
    }
  }

  const handleRemoveFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
    setError(null)
  }

  const handleClose = () => {
    if (isUploading) return
    setFiles([])
    setError(null)
    setIsDragging(false)
    setUploadProgress(null)
    onClose()
  }

  const handleUpload = async () => {
    if (files.length === 0 || isUploading) return
    if (faltaContrato) {
      setError('Selecione o contrato do lote.')
      return
    }

    // Fecha o modal imediatamente e delega o envio + acompanhamento em tempo real ao painel do Header
    if (onUploadFiles) {
      const selected = [...files]
      setFiles([])
      setError(null)
      setIsDragging(false)
      onClose()
      onUploadFiles(selected, contratoSelecionado)
      return
    }

    setIsUploading(true)
    setError(null)
    setUploadProgress({ current: 0, total: files.length })

    const remainingFiles = [...files]

    try {
      for (let i = 0; i < files.length; i++) {
        const currentFile = files[i]
        setUploadProgress({ current: i + 1, total: files.length })
        const response = await apiService.uploadLote(currentFile, contratoSelecionado)
        onSuccessUpload(currentFile.name, response.lote_id)
        remainingFiles.shift()
      }

      setIsUploading(false)
      setUploadProgress(null)
      setFiles([])
      onClose()
    } catch (err) {
      setIsUploading(false)
      setUploadProgress(null)
      setFiles(remainingFiles)
      setError(err instanceof Error ? err.message : 'Falha ao enviar arquivo(s)')
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-xs"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      <div className="w-full max-w-xl max-h-[calc(100dvh-2rem)] overflow-y-auto rounded-2xl bg-white dark:bg-[#1a1120] border border-[#ebe5ef] dark:border-[#2f1e39] p-6 shadow-2xl relative animate-in fade-in zoom-in-95 duration-200">
        <button
          onClick={handleClose}
          disabled={isUploading}
          className="absolute top-4 right-4 p-1.5 rounded-lg text-[#6e6378] dark:text-[#a093a8] hover:bg-[#f5eef7] dark:hover:bg-[#281831] disabled:opacity-40 transition-colors cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>

        <h3 className="text-lg font-bold text-[#2d0a33] dark:text-[#f8f5fc]">
          Enviar Lote de Documentos
        </h3>
        <p className="text-xs text-[#6e6378] dark:text-[#9f91a6] mt-0.5">
          Arraste e solte um ou vários PDFs/imagens ou clique para selecionar do computador
        </p>

        <div className="mt-5 space-y-4">
            {!empresaPropria && (
            <div>
              <label
                htmlFor="upload-contrato"
                className="block text-xs font-semibold text-[#2d0a33] dark:text-white mb-1"
              >
                Contrato{contratoObrigatorio ? '' : ' (opcional)'}
              </label>
              <select
                id="upload-contrato"
                value={contratoId}
                onChange={(e) => setContratoId(e.target.value)}
                disabled={isUploading}
                className="w-full px-3 py-2 rounded-xl text-xs bg-white dark:bg-[#150c18] border border-[#dcd4e2] dark:border-[#3d2948] text-[#2d0a33] dark:text-white focus:outline-none focus:ring-1 focus:ring-[#9333ea]"
              >
                <option value="">{contratoObrigatorio ? 'Selecione um contrato' : 'Sem contrato'}</option>
                {contratos.map((c) => (
                  <option key={c.id} value={c.id}>
                    {contratoLabel(c)}
                  </option>
                ))}
              </select>
              {contratoSelecionadoTexto && (
                <p className="mt-1.5 text-xs text-[#6e6378] dark:text-[#a093a8] break-words">{contratoSelecionadoTexto}</p>
              )}
              {contratoObrigatorio && contratosCarregados && contratos.length === 0 && (
                <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">
                  Nenhum contrato ativo disponível para envio. Fale com a equipe da plataforma.
                </p>
              )}
              {contratosErro && (
                <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">{contratosErro}</p>
              )}
            </div>
            )}

            <label
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-6 flex flex-col items-center justify-center cursor-pointer transition-all ${
                isDragging
                  ? 'border-[#9333ea] dark:border-[#c026d3] bg-[#f6ebfa] dark:bg-[#281530] scale-[1.01]'
                  : 'border-[#dcd4e2] dark:border-[#3d2948] hover:border-[#9333ea] dark:hover:border-[#c026d3] bg-[#fdfbfe] dark:bg-[#150c18]'
              }`}
            >
              <UploadCloud
                className={`w-10 h-10 mb-2 transition-transform ${
                  isDragging
                    ? 'text-[#7e22ce] dark:text-[#e879f9] scale-110'
                    : 'text-[#9333ea] dark:text-[#c026d3]'
                }`}
              />
              <span className="text-sm font-semibold text-[#2d0a33] dark:text-white text-center">
                {isDragging
                  ? 'Solte os arquivos aqui'
                  : 'Clique ou arraste um ou mais PDFs / imagens'}
              </span>
              <span className="text-xs text-[#8f8298] dark:text-[#7f7188] mt-1 text-center">
                PDF, JPEG, PNG ou TIFF · Suporta envio de múltiplos arquivos (máx. {MAX_UPLOAD_MB} MB cada)
              </span>
              <input
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png,.tif,.tiff"
                className="hidden"
                onChange={handleFileChange}
                disabled={isUploading}
              />
            </label>

            {error && (
              <div className="p-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/50 flex items-center gap-2 text-red-600 dark:text-red-400">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span className="text-[11px] font-medium leading-tight">
                  {error}
                </span>
              </div>
            )}

            {files.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-[#6e6378] dark:text-[#a093a8] px-1">
                  <span className="font-semibold">
                    {files.length} arquivo{files.length > 1 ? 's' : ''} selecionado{files.length > 1 ? 's' : ''}
                  </span>
                  {!isUploading && files.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setFiles([])}
                      className="text-[11px] text-[#9333ea] dark:text-[#d67bf3] hover:underline cursor-pointer"
                    >
                      Limpar todos
                    </button>
                  )}
                </div>

                <div className="max-h-44 overflow-y-auto space-y-2 pr-1">
                  {files.map((item, idx) => (
                    <div
                      key={`${item.name}-${item.size}-${item.lastModified}-${idx}`}
                      className="p-2.5 rounded-xl bg-[#f6ebfa] dark:bg-[#281530] border border-[#d88cf5]/40 dark:border-[#c026d3]/40 flex items-center justify-between gap-2"
                    >
                      <div className="flex items-center gap-2 overflow-hidden">
                        <File className="w-4 h-4 text-[#9333ea] dark:text-[#d67bf3] shrink-0" />
                        <span className="text-xs font-semibold text-[#2d0a33] dark:text-white truncate">
                          {item.name}
                        </span>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <span className="text-[11px] text-[#8f8298] dark:text-[#9f91a6]">
                          {(item.size / (1024 * 1024)).toFixed(2)} MB
                        </span>
                        {!isUploading && (
                          <button
                            type="button"
                            onClick={() => handleRemoveFile(idx)}
                            aria-label={`Remover ${item.name}`}
                            className="p-1 rounded-lg text-[#8f8298] hover:text-red-600 dark:hover:text-red-400 hover:bg-white/50 dark:hover:bg-black/20 transition-colors cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={isUploading}
                onClick={handleClose}
                className="px-4 py-2 rounded-xl text-xs sm:text-sm font-medium text-[#6e6378] dark:text-[#a093a8] hover:bg-[#f5eef7] dark:hover:bg-[#281831] disabled:opacity-50 transition-colors cursor-pointer"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={files.length === 0 || isUploading || faltaContrato}
                onClick={handleUpload}
                className="px-5 py-2 rounded-xl text-xs sm:text-sm font-bold text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] disabled:opacity-50 flex items-center gap-2 shadow-sm transition-all cursor-pointer"
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>
                      {uploadProgress && uploadProgress.total > 1
                        ? `Enviando ${uploadProgress.current}/${uploadProgress.total}...`
                        : 'Processando...'}
                    </span>
                  </>
                ) : (
                  <span>
                    {files.length > 1
                      ? `Enviar ${files.length} arquivos para IA`
                      : 'Enviar para IA'}
                  </span>
                )}
              </button>
            </div>
          </div>
      </div>
    </div>
  )
}
