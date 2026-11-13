import type { Company } from '../types';
import type { AnalisePonto } from '../components/auditoriaPonto';

const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000').replace(/\/+$/, '');
const API_PREFIX = import.meta.env.VITE_API_PREFIX ?? '';

export const BASE_URL = `${API_URL}${API_PREFIX}`;

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

/** Baixa o PDF recortado do documento com o nome padronizado. */
export const downloadDocumento = async (documentoId: number, fallbackFilename: string): Promise<void> => {
  const response = await authFetch(`/documentos/${documentoId}/download`);
  if (!response.ok) {
    throw new Error('Falha ao baixar documento');
  }
  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="([^"]+)"/i);
  const filename = match?.[1] || fallbackFilename;
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
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

export interface TipoDocumentoResponse {
  slug: string;
  nome: string;
  icone: 'car' | 'hash' | 'idcard' | 'home' | 'file' | 'briefcase';
}

export interface LoteResponse {
  lote_id: number;
  estado: string;
  existente: boolean;
  empresa_id?: number | null;
}

export interface DocumentoResponse {
  id: number;
  lote_id: number;
  ordem: number;
  pagina_ini: number;
  pagina_fim: number;
  estado: string;
  tipo: string | null;
  confianca: number | null;
  segmentacao_ambigua?: boolean;
  probabilidades?: Record<string, number> | null;
  tipo_original?: string | null;
  empresa_id?: number | null;
  campos?: Record<string, string>;
  pessoa?: string | null;
  nome_arquivo?: string;
  nome_original?: string;
  n_paginas?: number;
  processado_em?: string;
  paginas: { numero: number; imagem_url?: string; texto_ocr?: string | null }[];
}

export interface GrupoDocumentoResponse {
  tipo: string;
  total: number;
  documentos: DocumentoResponse[];
}

export interface DocumentosAgrupadosResponse {
  grupos: GrupoDocumentoResponse[];
}

export interface LoteEventoProgresso {
  lote_id: number;
  etapa: string;
  mensagem: string;
  timestamp: string;
  pagina_atual?: number;
  total_paginas?: number;
  total_documentos?: number;
  docs_pendentes?: number;
  documento_id?: number;
  tipo?: string | null;
  estado_documento?: string;
}

export interface LoteStatusResponse {
  id: number;
  nome_arquivo: string;
  estado: string;
  docs_pendentes: number;
  empresa_id?: number | null;
  documentos: DocumentoResponse[];
  ultimo_evento?: LoteEventoProgresso | null;
  historico_eventos?: LoteEventoProgresso[];
}

export interface RevisaoItemResponse {
  id: number;
  lote_id: number;
  tipo_sugerido: string | null;
  confianca: number | null;
  motivo: string | null;
  imagem_url: string;
  pagina_ini: number;
  pagina_fim: number;
  campos: Record<string, string>;
  pessoa: string | null;
  nome_arquivo: string;
  n_paginas: number;
  processado_em: string;
}

export interface SearchResult {
  lote_id: number;
  pagina: number;
  trecho: string;
  documento_id: number | null;
  tipo: string | null;
  nome_arquivo: string;
}

export interface DivergenciaPontoResponse {
  tipo?: string;
  data?: string | null;
  minutos?: number | null;
  base_legal?: string;
  detalhe?: string;
  evidencia?: string;
  campo?: string;
}

export interface ScoreDimensaoPonto {
  score?: number;
  confianca?: number;
  n_niveis?: number;
  normalizado?: number | null;
  indeterminada?: boolean;
  nao_avaliada?: boolean;
  motivo?: string | null;
}

export interface TotaisPontoResponse {
  trabalhado_min?: number;
  extras_min?: number;
  extras_bruto_min?: number;
  noturno_real_min?: number;
  noturno_computado_min?: number;
  dias_validos?: number;
  dias_invalidos?: number;
}

export interface PontoBritanicoResponse {
  conclusivo?: boolean;
  sinal_risco?: boolean | null;
  dias?: number;
  fracao_uniforme?: number | null;
}

export interface AnalisePontoResponse {
  documento_id: number;
  estado: 'pendente' | 'concluida' | 'erro' | string;
  erro?: string | null;
  score_geral?: number | null;
  requer_revisao?: boolean;
  scores_dimensao?: Record<string, ScoreDimensaoPonto> | null;
  totais?: TotaisPontoResponse | null;
  ponto_britanico?: PontoBritanicoResponse | null;
  intervalo_pre_assinalado?: boolean | null;
  divergencias?: DivergenciaPontoResponse[] | null;
  analise?: string | null;
}

export interface RevisaoResultResponse {
  id: number;
  estado: string;
  tipo: string;
  tipo_original: string | null;
  revisor: string;
  revisado_em: string;
}

export interface CadastroEmpresaResponse {
  id: number;
  nome: string;
  criado_em: string;
  n_lotes: number;
  n_documentos: number;
  lotes: { id: number; nome_arquivo: string; estado: string }[];
  documentos: {
    id: number;
    lote_id: number;
    ordem: number;
    pagina_ini: number;
    pagina_fim: number;
    tipo: string | null;
    estado: string;
  }[];
}

async function parseErrorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const error = await response.json();
    if (typeof error?.detail === 'string') {
      return error.detail;
    }
    if (Array.isArray(error?.detail) && error.detail.length > 0) {
      return error.detail.map((item: { msg?: string }) => item.msg || JSON.stringify(item)).join('; ');
    }
  } catch {
    // ignore JSON parse errors
  }
  return fallback;
}

export const apiService = {
  /**
   * Obtém a lista oficial de tipos documentais configurados no backend
   */
  getTipos: async (): Promise<TipoDocumentoResponse[]> => {
    const response = await authFetch(`/tipos`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar tipos documentais'));
    }
    return response.json();
  },

  /**
   * Monta a URL da imagem PNG de uma página de lote
   */
  getPageImageUrl: (loteId: number, numeroPagina: number): string => {
    return `${BASE_URL}/lotes/${loteId}/paginas/${numeroPagina}/imagem`;
  },

  /**
   * Faz upload de um arquivo (PDF, JPEG, PNG ou TIFF) para criar um novo lote
   */
  uploadLote: async (file: File, empresaId?: number): Promise<LoteResponse> => {
    const formData = new FormData();
    formData.append('arquivo', file);
    if (empresaId !== undefined) {
      formData.append('empresa_id', String(empresaId));
    }

    const response = await authFetch(`/lotes`, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao fazer upload do arquivo'));
    }

    return response.json();
  },

  /**
   * Obtém o status e os documentos de um lote específico
   */
  getLoteStatus: async (loteId: number): Promise<LoteStatusResponse> => {
    const response = await authFetch(`/lotes/${loteId}`);

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao obter status do lote'));
    }

    return response.json();
  },

  /**
   * Cancela o processamento de um lote em andamento
   */
  cancelLote: async (loteId: number): Promise<LoteStatusResponse> => {
    const response = await authFetch(`/lotes/${loteId}/cancelar`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cancelar lote'));
    }

    return response.json();
  },

  /**
   * Reprocessa um lote que falhou ou foi cancelado a partir do arquivo original salvo no servidor
   */
  retryLote: async (loteId: number): Promise<LoteStatusResponse> => {
    const response = await authFetch(`/lotes/${loteId}/reprocessar`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao reprocessar lote'));
    }

    return response.json();
  },

  /**
   * Assina o stream SSE (Server-Sent Events) de progresso em tempo real de um lote
   */
  streamLoteEvents: async (
    loteId: number,
    onEvent: (payload: LoteStatusResponse) => void,
    signal: AbortSignal
  ): Promise<void> => {
    const response = await authFetch(`/lotes/${loteId}/eventos`, {
      headers: { Accept: 'text/event-stream' },
      signal,
    });

    if (!response.ok || !response.body) {
      throw new Error(await parseErrorMessage(response, 'Erro ao conectar ao stream de eventos'));
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    const processarBlocoSse = (rawEvent: string) => {
      const dataLines: string[] = [];
      for (const line of rawEvent.split('\n')) {
        const trimmed = line.trimEnd();
        if (!trimmed || trimmed.startsWith(':')) {
          continue; // ignora linhas em branco e frames de keepalive/comentário
        }
        if (trimmed.startsWith('data:')) {
          dataLines.push(trimmed.slice(5).trimStart());
        }
      }
      if (dataLines.length === 0) return;
      try {
        const parsed = JSON.parse(dataLines.join('\n')) as LoteStatusResponse;
        if (
          parsed &&
          typeof parsed === 'object' &&
          typeof parsed.id === 'number' &&
          typeof parsed.estado === 'string'
        ) {
          onEvent(parsed);
        }
      } catch {
        // ignora payload parcial ou JSON inválido sem interromper o stream
      }
    };

    try {
      while (!signal.aborted) {
        const { value, done } = await reader.read();
        if (done) {
          buffer += decoder.decode().replace(/\r\n/g, '\n');
          if (buffer.trim()) {
            processarBlocoSse(buffer);
          }
          break;
        }
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n');

        let boundary = buffer.indexOf('\n\n');
        while (boundary !== -1) {
          const rawEvent = buffer.slice(0, boundary);
          buffer = buffer.slice(boundary + 2);
          processarBlocoSse(rawEvent);
          boundary = buffer.indexOf('\n\n');
        }
      }
    } finally {
      try {
        await reader.cancel();
      } catch {
        // ignore
      }
      try {
        reader.releaseLock();
      } catch {
        // ignore
      }
    }
  },

  /**
   * Realiza uma busca textual nos documentos processados
   */
  search: async (query: string, limit: number = 20): Promise<SearchResult[]> => {
    const params = new URLSearchParams({ q: query, limite: limit.toString() });
    const response = await authFetch(`/busca?${params}`);

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao realizar busca'));
    }

    return response.json();
  },

  /**
   * Obtém a fila de documentos que aguardam revisão manual
   */
  getReviewQueue: async (): Promise<RevisaoItemResponse[]> => {
    const response = await authFetch(`/revisao`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao obter fila de revisão'));
    }
    return response.json();
  },

  /**
   * Submete a revisão de um documento (estado 'em_revisao' ou 'revisado')
   */
  submitReview: async (documentoId: number, tipo: string, revisor: string): Promise<RevisaoResultResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/revisao`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo, revisor }),
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao submeter revisão'));
    }

    return response.json();
  },

  /**
   * Atualiza o tipo de um documento em qualquer estado exceto 'segmentado' e 'erro'
   */
  updateDocumentTipo: async (documentoId: number, tipo: string, revisor: string): Promise<DocumentoResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/tipo`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo, revisor }),
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao atualizar tipo do documento'));
    }

    return response.json();
  },

  /**
   * Atualiza ou remove campos extraídos de um documento
   */
  updateDocumentCampos: async (
    documentoId: number,
    campos: Record<string, string | null>,
    revisor: string
  ): Promise<DocumentoResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/campos`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campos, revisor }),
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao atualizar campos do documento'));
    }

    return response.json();
  },

  /**
   * Exclui um documento (lote precisa estar concluído ou em erro)
   */
  deleteDocument: async (documentoId: number): Promise<void> => {
    const response = await authFetch(`/documentos/${documentoId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao excluir documento'));
    }
  },

  /**
   * Obtém os detalhes de um documento específico
   */
  getDocumentDetails: async (documentoId: number): Promise<DocumentoResponse> => {
    const response = await authFetch(`/documentos/${documentoId}`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Documento não encontrado'));
    }
    return response.json();
  },

  /**
   * Obtém os documentos agrupados por tipo
   */
  getDocumentosAgrupados: async (
    empresaId?: number,
    falhou?: boolean
  ): Promise<DocumentosAgrupadosResponse> => {
    const searchParams = new URLSearchParams();
    if (empresaId !== undefined) {
      searchParams.set('empresa_id', String(empresaId));
    }
    if (falhou !== undefined) {
      searchParams.set('falhou', String(falhou));
    }
    const query = searchParams.toString();
    const response = await authFetch(`/documentos${query ? `?${query}` : ''}`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar documentos'));
    }
    return response.json();
  },

  /**
   * Obtém a análise de folha de ponto de um documento
   */
  getAnalisePonto: async (documentoId: number): Promise<AnalisePonto> => {
    const response = await authFetch(`/documentos/${documentoId}/analise-ponto`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Análise não encontrada'));
    }
    return response.json();
  },

  /**
   * Obtém a lista de empresas prestadoras e seus scores de conformidade
   */
  getEmpresas: async (): Promise<Company[]> => {
    const response = await authFetch(`/empresas`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar empresas'));
    }
    return response.json();
  },

  /**
   * Obtém os três níveis de conformidade de uma empresa pelo CNPJ
   */
  getEmpresaConformidade: async (cnpj: string): Promise<Record<string, unknown>> => {
    const response = await authFetch(`/empresas/${encodeURIComponent(cnpj)}/conformidade`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao obter conformidade da empresa'));
    }
    return response.json();
  },

  /**
   * Obtém as empresas cadastradas
   */
  getCadastroEmpresas: async (): Promise<CadastroEmpresaResponse[]> => {
    const response = await authFetch(`/cadastro-empresas`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar cadastro de empresas'));
    }
    return response.json();
  },

  /**
   * Cadastra uma nova empresa pelo nome
   */
  createCadastroEmpresa: async (nome: string): Promise<CadastroEmpresaResponse> => {
    const response = await authFetch(`/cadastro-empresas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome }),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar empresa'));
    }
    return response.json();
  },

  /**
   * Verifica a saúde do backend
   */
  checkHealth: async (): Promise<{ status: string }> => {
    const response = await authFetch(`/health`);
    if (!response.ok) {
      throw new Error('Backend indisponível');
    }
    return response.json();
  },
};
