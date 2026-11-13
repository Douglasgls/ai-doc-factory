export interface DocumentCategory {
  id: string
  name: string
  count: number
  totalPercentage: number
  icon: 'car' | 'hash' | 'idcard' | 'home' | 'file' | 'briefcase' | 'shield'
  slug: string
  score?: number
  classificacao?: 'Regular' | 'Atenção' | 'Crítico'
  provisorio?: boolean
}

export interface Company {
  cnpj: string
  razao_social: string
  score: number
  classificacao: 'Regular' | 'Atenção' | 'Crítico'
  provisorio: boolean
  documentos_por_tipo: Record<string, number>
}

export interface DetailedDocument {
  id: string
  loteId?: number
  filename: string
  originalFilename?: string
  category: string
  estado?: string
  personName: string
  pages: number
  startPage?: number
  processedDate: string
  processedTimestamp?: number
  confidence: number
  campos?: Record<string, string>
  metadata: {
    registrationNumber?: string
    categoryType?: string
    expirationDate?: string
    cpfNumber?: string
    rgNumber?: string
    address?: string
    admissionDate?: string
    examDate?: string
    companyName?: string
    companyCnpj?: string
  }
}

export interface ReviewPendingDocument {
  id: string
  loteId: number
  filename: string
  issueType: 'baixa_qualidade' | 'conteudo_ilegivel' | 'confiança_baixa'
  issueLabel: string
  timeAgo: string
  isPriority?: boolean
  processedDate: string
  processedTimestamp?: number
  pages: number
  startPage: number
  issueDescription: string
  suggestedType: string
  suggestedTypeLabel?: string
  suggestedConfidence: number
  extractedFields: { key: string; value: string }[]
  initialCampos?: Record<string, string>
  personName: string
}

// Aliases para retrocompatibilidade
export type StoredDocument = DetailedDocument
export type ReviewDocument = ReviewPendingDocument
