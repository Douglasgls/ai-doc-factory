export interface DocumentCategory {
  id: string
  name: string
  count: number
  totalPercentage: number
  icon: 'car' | 'hash' | 'idcard' | 'home' | 'file' | 'briefcase'
  slug: string
}

export interface DetailedDocument {
  id: string
  filename: string
  category: string
  personName: string
  pages: number
  processedDate: string
  confidence: number
  metadata: {
    registrationNumber?: string
    categoryType?: string
    expirationDate?: string
    cpfNumber?: string
    rgNumber?: string
    address?: string
  }
}

export interface ReviewPendingDocument {
  id: string
  filename: string
  issueType: 'baixa_qualidade' | 'conteudo_ilegivel' | 'confiança_baixa'
  issueLabel: string
  timeAgo: string
  isPriority?: boolean
  processedDate: string
  pages: number
  issueDescription: string
  suggestedType: string
  suggestedConfidence: number
  extractedFields: { key: string; value: string }[]
  personName: string
  imagemUrl?: string
  loteId?: number
  paginaIni?: number
}

// Aliases para retrocompatibilidade
export type StoredDocument = DetailedDocument
export type ReviewDocument = ReviewPendingDocument
