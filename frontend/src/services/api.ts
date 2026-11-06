import type { Company } from '../types';

const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000';
const API_PREFIX = import.meta.env.VITE_API_PREFIX || '';

const BASE_URL = `${API_URL}${API_PREFIX}`;

const TOKEN_KEY = 'auth_token';
/** Disparado em qualquer 401: o App limpa o estado e mostra o login. */
export const AUTH_EXPIRED_EVENT = 'auth:expired';

export const authToken = {
  get: (): string | null => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

/**
 * Único ponto de saída das chamadas autenticadas: coloca Authorization: Bearer em todas
 * (inclusive upload) e, em 401, limpa o token e avisa o App para voltar ao login.
 */
export const authFetch = async (path: string, init: RequestInit = {}): Promise<Response> => {
  const headers = new Headers(init.headers);
  const token = authToken.get();
  if (token) headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers });
  if (response.status === 401) {
    authToken.clear();
    window.dispatchEvent(new Event(AUTH_EXPIRED_EVENT));
    throw new Error('Sessão expirada. Entre novamente.');
  }
  return response;
};

/** Baixa a imagem de uma página com o cabeçalho de autenticação (<img src> não envia cabeçalho). */
export const fetchPageImage = async (loteId: number, pagina: number, signal?: AbortSignal): Promise<Blob> => {
  const response = await authFetch(`/lotes/${loteId}/paginas/${pagina}/imagem`, { signal });
  if (!response.ok) throw new Error('Imagem indisponível');
  return response.blob();
};

export interface LoginResponse {
  access_token: string;
  token_type: string;
  expira_em: string;
}

/** Login: não passa por authFetch, porque um 401 aqui é senha errada e não sessão expirada. */
export const login = async (usuario: string, senha: string): Promise<LoginResponse> => {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ usuario, senha }),
    });
  } catch {
    throw new Error('Não foi possível conectar ao servidor.');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Erro ao entrar.');
  }
  const data: LoginResponse = await response.json();
  authToken.set(data.access_token);
  return data;
};

export interface LoteResponse {
  lote_id: number;
  estado: string;
  existente: boolean;
}

export interface DocumentoResponse {
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
}

export interface LoteStatusResponse {
  id: number;
  nome_arquivo: string;
  estado: string;
  docs_pendentes: number;
  documentos: DocumentoResponse[];
}

export interface SearchResult {
  lote_id: number;
  pagina: number;
  trecho: string;
}

export const apiService = {
  /**
   * Faz upload de um arquivo para criar um novo lote
   */
  uploadLote: async (file: File): Promise<LoteResponse> => {
    const formData = new FormData();
    formData.append('arquivo', file);

    const response = await authFetch(`/lotes`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Erro ao fazer upload do arquivo');
    }

    return response.json();
  },

  /**
   * Obtém o status e os documentos de um lote específico
   */
  getLoteStatus: async (loteId: number): Promise<LoteStatusResponse> => {
    const response = await authFetch(`/lotes/${loteId}`);

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Erro ao obter status do lote');
    }

    return response.json();
  },

  /**
   * Realiza uma busca textual nos documentos processados
   */
  search: async (query: string, limit: number = 20): Promise<SearchResult[]> => {
    const params = new URLSearchParams({ q: query, limite: limit.toString() });
    const response = await authFetch(`/busca?${params}`);

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Erro ao realizar busca');
    }

    return response.json();
  },

  /**
   * Obtém a fila de documentos que aguardam revisão manual
   */
  getReviewQueue: async (): Promise<any[]> => {
    const response = await authFetch(`/revisao`);
    if (!response.ok) throw new Error('Erro ao obter fila de revisão');
    return response.json();
  },

  /**
   * Submete a revisão de um documento
   */
  submitReview: async (documentoId: number, tipo: string, revisor: string): Promise<any> => {
    const response = await authFetch(`/documentos/${documentoId}/revisao`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo, revisor }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Erro ao submeter revisão');
    }

    return response.json();
  },

  /**
   * Obtém os detalhes de um documento específico
   */
  getDocumentDetails: async (documentoId: number): Promise<any> => {
    const response = await authFetch(`/documentos/${documentoId}`);
    if (!response.ok) throw new Error('Documento não encontrado');
    return response.json();
  },

  /**
   * Obtém os documentos agrupados por tipo
   */
  getDocumentosAgrupados: async (empresaId?: number): Promise<{ grupos: any[] }> => {
    const params = empresaId ? `?empresa_id=${empresaId}` : '';
    const response = await authFetch(`/documentos${params}`);
    if (!response.ok) throw new Error('Erro ao listar documentos');
    return response.json();
  },

  /**
   * Obtém a análise de folha de ponto de um documento
   */
  getAnalisePonto: async (documentoId: number): Promise<any> => {
    const response = await authFetch(`/documentos/${documentoId}/analise-ponto`);
    if (!response.ok) throw new Error('Análise não encontrada');
    return response.json();
  },

  /**
   * Obtém a lista de empresas e seus scores de conformidade
   */
  getEmpresas: async (): Promise<Company[]> => {
    const response = await authFetch(`/empresas`);
    if (!response.ok) throw new Error('Erro ao listar empresas');
    return response.json();
  },

  /**
   * Verifica a saúde do backend
   */
  checkHealth: async (): Promise<{ status: string }> => {
    const response = await authFetch(`/health`);
    if (!response.ok) throw new Error('Backend indisponível');
    return response.json();
  }
};
