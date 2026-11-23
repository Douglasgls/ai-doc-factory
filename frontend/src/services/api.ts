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

/**
 * Rotas públicas do convite: sem Authorization e sem authFetch (um 404 aqui é convite inválido e
 * um 401 nunca deve derrubar uma sessão). O token vai no caminho; nunca é logado nem guardado.
 */
export const consultarConvite = async (token: string): Promise<ConvitePublico | null> => {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/convites/${encodeURIComponent(token)}`);
  } catch {
    throw new Error('Não foi possível conectar ao servidor.');
  }
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(await parseErrorMessage(response, 'Erro ao consultar o convite.'));
  return response.json();
};

/** Aceita o convite e já guarda o token de login (mesmo formato do /auth/login). */
export const aceitarConvite = async (token: string, nome: string, senha: string): Promise<LoginResponse> => {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}/convites/${encodeURIComponent(token)}/aceitar`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome, senha }),
    });
  } catch {
    throw new Error('Não foi possível conectar ao servidor.');
  }
  if (response.status === 404) throw new ConviteInvalidoError();
  if (!response.ok) throw new Error(await parseErrorMessage(response, 'Erro ao criar o acesso.'));
  const data: LoginResponse = await response.json();
  authToken.set(data.access_token);
  return data;
};

export class ConviteInvalidoError extends Error {
  constructor() {
    super('Este convite não é válido, já foi usado ou expirou. Peça um novo a quem te convidou.');
  }
}

export interface TipoDocumentoResponse {
  slug: string;
  nome: string;
  icone: 'car' | 'hash' | 'idcard' | 'home' | 'file' | 'briefcase';
}

export interface LoteResponse {
  lote_id: number;
  estado: string;
  existente: boolean;
  contrato_id?: number | null;
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
  modelo?: string | null;
  versao_prompt?: string | null;
  segunda_opiniao?: { modelo?: string; versao_prompt?: string; tipo?: string | null; status?: string } | null;
  tipo_original?: string | null;
  contrato_id?: number | null;
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
  contrato_id?: number | null;
  documentos: DocumentoResponse[];
  ultimo_evento?: LoteEventoProgresso | null;
  historico_eventos?: LoteEventoProgresso[];
}

export interface LoteResumoResponse {
  id: number;
  nome_arquivo: string;
  estado: string;
  docs_pendentes: number;
  contrato_id: number | null;
  criado_em: string;
  total_documentos: number;
  em_revisao: number;
  com_erro: number;
}

export interface LotesListadosResponse {
  itens: LoteResumoResponse[];
  proximo_cursor: number | null;
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

export interface UsuarioAtual {
  id: number;
  email: string;
  nome: string;
  nivel: string; // 'plataforma' | 'tomador' | 'prestador'
  papel: string;
  tomador_id: number | null;
  prestador_id: number | null;
}

export interface Tomador {
  id: number;
  nome: string;
  cnpj: string | null;
  ativo: boolean;
  criado_em: string;
}
export interface NovoTomador {
  nome: string;
  cnpj?: string | null;
}

export interface Prestador {
  id: number;
  cnpj: string;
  razao_social: string;
  ativo: boolean;
  criado_em: string;
}
export interface NovoPrestador {
  cnpj: string;
  razao_social: string;
}

export interface Contrato {
  id: number;
  tomador_id: number;
  prestador_id: number;
  ativo: boolean;
  vigencia_inicio: string | null;
  vigencia_fim: string | null;
  criado_em: string;
  tomador_nome: string;
  tomador_ativo: boolean;
  prestador_razao_social: string;
  prestador_cnpj: string;
  prestador_ativo: boolean;
  acesso_prestador?: 'ativo' | 'convite_pendente' | 'sem_acesso';
  perfil_jornada: string;
  /** Empresa solo: o mesmo CNPJ é tomador e prestador (sem terceirização). */
  proprio?: boolean;
}

export interface PerfilJornadaResumo {
  perfil: string;
  padrao: boolean;
  parametros_proprios: number;
  contratos: number;
}
export interface ParametroProprio {
  parametro: string;
  valor: number;
  unidade: string;
  base_legal: string;
  vigente_desde: string | null;
}
export interface ParametroEfetivo {
  valor: number;
  base_legal: string;
  vigencias?: { desde: string; valor: number; base_legal: string }[];
}
export interface PerfilJornadaDetalhe {
  perfil: string;
  padrao: boolean;
  proprios: ParametroProprio[];
  efetivo: Record<string, ParametroEfetivo>;
}
export interface ParametroEntrada {
  parametro: string;
  valor: number;
  base_legal: string;
  vigente_desde: string | null;
}
export interface NovoContrato {
  tomador_id: number;
  prestador_id: number;
  vigencia_inicio?: string | null;
  vigencia_fim?: string | null;
}

export interface NovoConvite {
  email: string;
  nivel: 'plataforma' | 'tomador' | 'prestador';
  papel: 'admin' | 'membro';
  tomador_id?: number | null;
  prestador_id?: number | null;
}
/** Resposta de POST /convites: o token só existe aqui. */
export interface ConviteCriado {
  id: number;
  email: string;
  nivel: string;
  papel: string;
  expira_em: string;
  token: string;
}
export interface ConviteListado {
  id: number;
  email: string;
  nivel: string;
  papel: string;
  tomador_id: number | null;
  prestador_id: number | null;
  organizacao_nome: string | null;
  estado: 'pendente' | 'usado' | 'expirado';
  criado_por: number | null;
  criado_em: string;
  expira_em: string;
  usado_em: string | null;
  usuario_id: number | null;
}
export interface ConvitePublico {
  email: string;
  nivel: string;
  organizacao_nome: string | null;
  expira_em: string;
}
export interface NovaTerceirizada {
  cnpj: string;
  razao_social: string;
  email: string;
  tomador_id?: number | null;
}
export interface TerceirizadaCadastrada {
  contrato: { id: number; ativo: boolean };
  prestador: { id: number; cnpj: string; razao_social: string };
  acesso: 'convite_criado' | 'convite_pendente' | 'ja_tem_acesso';
  convite: { id: number; email: string; expira_em: string; token: string } | null;
}
export interface NovaEmpresaPropria {
  cnpj: string;
  razao_social: string;
  email_admin: string;
}
export interface EmpresaPropriaCadastrada {
  contrato: { id: number; ativo: boolean; proprio: boolean };
  tomador: { id: number; cnpj: string; nome: string };
  prestador: { id: number; cnpj: string; nome: string };
  acesso: 'convite_criado' | 'convite_pendente' | 'ja_tem_acesso';
  convite: { id: number; email: string; expira_em: string; token: string } | null;
}
export interface UsuarioListado {
  id: number;
  nome: string;
  email: string;
  nivel: string;
  papel: string;
  ativo: boolean;
  criado_em: string;
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
  uploadLote: async (file: File, contratoId?: number | null): Promise<LoteResponse> => {
    const formData = new FormData();
    formData.append('arquivo', file);
    if (contratoId !== undefined && contratoId !== null) {
      formData.append('contrato_id', String(contratoId));
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
   * Histórico de lotes do escopo do usuário (resumo), do mais novo para o mais antigo.
   */
  listLotes: async (
    opcoes: { limite?: number; antesDe?: number; estado?: string; contratoId?: number } = {}
  ): Promise<LotesListadosResponse> => {
    const params = new URLSearchParams();
    if (opcoes.limite !== undefined) params.set('limite', String(opcoes.limite));
    if (opcoes.antesDe !== undefined) params.set('antes_de', String(opcoes.antesDe));
    if (opcoes.estado !== undefined) params.set('estado', opcoes.estado);
    if (opcoes.contratoId !== undefined) params.set('contrato_id', String(opcoes.contratoId));
    const consulta = params.toString();
    const response = await authFetch(`/lotes${consulta ? `?${consulta}` : ''}`);

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar lotes'));
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
  submitReview: async (documentoId: number, tipo: string): Promise<RevisaoResultResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/revisao`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo }),
    });

    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao submeter revisão'));
    }

    return response.json();
  },

  /**
   * Atualiza o tipo de um documento em qualquer estado exceto 'segmentado' e 'erro'
   */
  updateDocumentTipo: async (documentoId: number, tipo: string): Promise<DocumentoResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/tipo`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tipo }),
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
    campos: Record<string, string | null>
  ): Promise<DocumentoResponse> => {
    const response = await authFetch(`/documentos/${documentoId}/campos`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ campos }),
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
    contratoId?: number,
    falhou?: boolean
  ): Promise<DocumentosAgrupadosResponse> => {
    const searchParams = new URLSearchParams();
    if (contratoId !== undefined) {
      searchParams.set('contrato_id', String(contratoId));
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

  getTomadores: async (): Promise<Tomador[]> => {
    const response = await authFetch(`/tomadores`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar tomadores'));
    }
    return response.json();
  },

  createTomador: async (dados: NovoTomador): Promise<Tomador> => {
    const response = await authFetch(`/tomadores`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar tomador'));
    }
    return response.json();
  },

  getPrestadores: async (): Promise<Prestador[]> => {
    const response = await authFetch(`/prestadores`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar prestadores'));
    }
    return response.json();
  },

  createPrestador: async (dados: NovoPrestador): Promise<Prestador> => {
    const response = await authFetch(`/prestadores`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar prestador'));
    }
    return response.json();
  },

  getContratos: async (): Promise<Contrato[]> => {
    const response = await authFetch(`/contratos`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar contratos'));
    }
    return response.json();
  },

  createContrato: async (dados: NovoContrato): Promise<Contrato> => {
    const response = await authFetch(`/contratos`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar contrato'));
    }
    return response.json();
  },

  getPerfisJornada: async (): Promise<PerfilJornadaResumo[]> => {
    const response = await authFetch(`/perfis-jornada`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar perfis de jornada'));
    }
    return response.json();
  },

  getPerfilJornada: async (perfil: string): Promise<PerfilJornadaDetalhe> => {
    const response = await authFetch(`/perfis-jornada/${encodeURIComponent(perfil)}`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao carregar o perfil de jornada'));
    }
    return response.json();
  },

  gravarPerfilJornada: async (perfil: string, parametros: ParametroEntrada[]): Promise<PerfilJornadaDetalhe> => {
    const response = await authFetch(`/perfis-jornada/${encodeURIComponent(perfil)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ parametros }),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao salvar o perfil de jornada'));
    }
    return response.json();
  },

  associarPerfilJornada: async (contratoId: number, perfil: string): Promise<Contrato> => {
    const response = await authFetch(`/contratos/${contratoId}/perfil-jornada`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ perfil }),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao trocar o perfil do contrato'));
    }
    return response.json();
  },

  criarConvite: async (dados: NovoConvite): Promise<ConviteCriado> => {
    const response = await authFetch(`/convites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao criar convite'));
    }
    return response.json();
  },

  getConvites: async (): Promise<ConviteListado[]> => {
    const response = await authFetch(`/convites`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar convites'));
    }
    return response.json();
  },

  getUsuarios: async (): Promise<UsuarioListado[]> => {
    const response = await authFetch(`/usuarios`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao listar usuários'));
    }
    return response.json();
  },

  cadastrarTerceirizada: async (dados: NovaTerceirizada): Promise<TerceirizadaCadastrada> => {
    const response = await authFetch(`/terceirizadas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar terceirizada'));
    }
    return response.json();
  },

  cadastrarEmpresaPropria: async (dados: NovaEmpresaPropria): Promise<EmpresaPropriaCadastrada> => {
    const response = await authFetch(`/empresas-proprias`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(dados),
    });
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao cadastrar empresa própria'));
    }
    return response.json();
  },

  /** Usuário logado (nível plataforma, tomador ou prestador). */
  getMe: async (): Promise<UsuarioAtual> => {
    const response = await authFetch(`/auth/me`);
    if (!response.ok) {
      throw new Error(await parseErrorMessage(response, 'Erro ao obter o usuário'));
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
