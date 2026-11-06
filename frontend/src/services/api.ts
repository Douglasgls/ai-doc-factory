/**
 * Cliente HTTP da API Document AI Factory
 */

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';
const API_PREFIX = import.meta.env.VITE_API_PREFIX || '';

export const BASE_URL = `${API_URL}${API_PREFIX}`.replace(/\/+$/, '');

export interface TipoInfoResponse {
  slug: string;
  nome: string;
  icone: 'car' | 'hash' | 'idcard' | 'home' | 'file' | 'briefcase';
}

export interface DocumentoCampoItem {
  campo: string;
  valor: string;
}

export interface DocumentoItemResponse {
  id: number;
  lote_id: number;
  ordem: number;
  pagina_ini: number;
  pagina_fim: number;
  estado: 'segmentado' | 'classificado' | 'em_revisao' | 'revisado' | 'erro';
  tipo: string | null;
  confianca: number;
  empresa_id: number | null;
  campos: Record<string, string>;
  pessoa: string | null;
  nome_arquivo: string;
  n_paginas: number;
  processado_em: string;
}

export interface GrupoDocumentosResponse {
  tipo: string;
  total: number;
  documentos: DocumentoItemResponse[];
}

export interface ListarDocumentosResponse {
  grupos: GrupoDocumentosResponse[];
}

export interface DocumentoRevisaoResponse {
  id: number;
  lote_id: number;
  tipo_sugerido: string;
  confianca: number;
  motivo: string;
  imagem_url: string;
  campos: Record<string, string>;
  pessoa?: string | null;
  nome_arquivo?: string;
  n_paginas?: number;
  processado_em?: string;
  pagina_ini?: number;
  pagina_fim?: number;
}

export interface DocumentoDetalheResponse extends DocumentoItemResponse {
  segmentacao_ambigua: boolean;
  tipo_original: string | null;
  revisor: string | null;
  revisado_em: string | null;
  motivo_revisao: string | null;
  probabilidades: Record<string, number> | null;
  paginas: {
    numero: number;
    imagem_url: string;
    texto: string | null;
  }[];
}

export interface LoteResponse {
  lote_id: number;
  estado: string;
  existente: boolean;
}

export interface LoteStatusResponse {
  id: number;
  nome_arquivo: string;
  estado: string;
  docs_pendentes: number;
  documentos: {
    id: number;
    ordem: number;
    pagina_ini: number;
    pagina_fim: number;
    estado: string;
    tipo: string | null;
    confianca: number;
    segmentacao_ambigua: boolean;
    probabilidades: Record<string, number> | null;
    tipo_original: string | null;
  }[];
}

export interface SearchResult {
  lote_id: number;
  pagina: number;
  trecho: string;
  documento_id?: number;
  tipo?: string;
  empresa_nome?: string;
}

export interface EmpresaResponse {
  id: number;
  nome: string;
  criado_em: string;
  score_conformidade?: number | null;
}

export const apiService = {
  /**
   * Verifica a saúde da API
   */
  checkHealth: async (): Promise<{ status: string }> => {
    const res = await fetch(`${BASE_URL}/health`);
    if (!res.ok) throw new Error('API indisponível');
    return res.json();
  },

  /**
   * Obtém a lista de tipos documentais configurados no backend
   */
  getTipos: async (): Promise<TipoInfoResponse[]> => {
    const res = await fetch(`${BASE_URL}/tipos`);
    if (!res.ok) throw new Error('Erro ao carregar tipos documentais');
    return res.json();
  },

  /**
   * Obtém os documentos agrupados por tipo
   */
  getDocumentos: async (empresaId?: number, falhou?: boolean): Promise<ListarDocumentosResponse> => {
    const params = new URLSearchParams();
    if (empresaId !== undefined) params.append('empresa_id', empresaId.toString());
    if (falhou !== undefined) params.append('falhou', falhou.toString());

    const url = `${BASE_URL}/documentos${params.toString() ? `?${params.toString()}` : ''}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error('Erro ao carregar documentos');
    return res.json();
  },

  /**
   * Obtém a fila de documentos aguardando revisão manual
   */
  getReviewQueue: async (): Promise<DocumentoRevisaoResponse[]> => {
    const res = await fetch(`${BASE_URL}/revisao`);
    if (!res.ok) throw new Error('Erro ao carregar fila de revisão');
    return res.json();
  },

  /**
   * Submete a revisão de um documento pendente
   */
  submitReview: async (
    documentoId: number,
    tipo: string,
    revisor: string = 'Operador'
  ): Promise<{ id: number; estado: string; tipo: string; revisor: string }> => {
    const res = await fetch(`${BASE_URL}/documentos/${documentoId}/revisao`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo, revisor }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao submeter revisão');
    }

    return res.json();
  },

  /**
   * Atualiza ou remove campos extraídos de um documento
   */
  atualizarCampos: async (
    documentoId: number,
    campos: Record<string, string | null>,
    revisor: string = 'Operador'
  ): Promise<DocumentoDetalheResponse> => {
    const res = await fetch(`${BASE_URL}/documentos/${documentoId}/campos`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campos, revisor }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao atualizar campos');
    }

    return res.json();
  },

  /**
   * Corrige o tipo de um documento já classificado
   */
  atualizarTipo: async (
    documentoId: number,
    tipo: string,
    revisor: string = 'Operador'
  ): Promise<{ id: number; estado: string; tipo: string }> => {
    const res = await fetch(`${BASE_URL}/documentos/${documentoId}/tipo`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo, revisor }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao atualizar tipo documental');
    }

    return res.json();
  },

  /**
   * Obtém detalhes completos de um documento específico (incluindo texto OCR e páginas)
   */
  getDocumentDetails: async (documentoId: number): Promise<DocumentoDetalheResponse> => {
    const res = await fetch(`${BASE_URL}/documentos/${documentoId}`);
    if (!res.ok) throw new Error('Documento não encontrado');
    return res.json();
  },

  /**
   * Faz upload de arquivo para criar um novo lote
   */
  uploadLote: async (file: File, empresaId?: number): Promise<LoteResponse> => {
    const formData = new FormData();
    formData.append('arquivo', file);
    if (empresaId !== undefined) {
      formData.append('empresa_id', empresaId.toString());
    }

    const res = await fetch(`${BASE_URL}/lotes`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Erro ao enviar lote de documentos');
    }

    return res.json();
  },

  /**
   * Consulta o status de processamento de um lote
   */
  getLoteStatus: async (loteId: number): Promise<LoteStatusResponse> => {
    const res = await fetch(`${BASE_URL}/lotes/${loteId}`);
    if (!res.ok) throw new Error('Lote não encontrado');
    return res.json();
  },

  /**
   * Realiza busca textual full-text
   */
  search: async (query: string, limit: number = 20): Promise<SearchResult[]> => {
    const params = new URLSearchParams({ q: query, limite: limit.toString() });
    const res = await fetch(`${BASE_URL}/busca?${params.toString()}`);
    if (!res.ok) throw new Error('Erro na busca');
    return res.json();
  },

  /**
   * Retorna a URL completa para a imagem escaneada de uma página
   */
  getImagemUrl: (loteId: number, numeroPagina: number): string => {
    return `${BASE_URL}/lotes/${loteId}/paginas/${numeroPagina}/imagem`;
  },
};
