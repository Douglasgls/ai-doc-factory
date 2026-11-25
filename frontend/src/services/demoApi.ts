import type {
  DocumentoResponse,
  DocumentosAgrupadosResponse,
  LoteStatusResponse,
  PerfilJornadaResumo,
  RevisaoItemResponse,
  SearchResult,
} from './api'
import {
  buildCompaniesSummary,
  createInitialDemoState,
  DEMO_PAGE_IMAGES,
  DEMO_TIPOS,
  DEMO_USUARIO,
  type DemoState,
} from './demoData'

const DEMO_SESSION_KEY = 'evidocs_demo_mode'

/**
 * Ativa o modo demo (100% em memória, sem backend) quando:
 * - VITE_DEMO_MODE=true no build/ambiente, OU
 * - a URL contém ?demo=1 (mantido na aba via sessionStorage).
 * Em produção oficial (sem a flag), retorna sempre false.
 */
export function isDemoMode(): boolean {
  if (import.meta.env.VITE_DEMO_MODE === 'true') return true
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  if (params.get('demo') === '1') {
    sessionStorage.setItem(DEMO_SESSION_KEY, '1')
    return true
  }
  if (params.get('demo') === '0') {
    sessionStorage.removeItem(DEMO_SESSION_KEY)
    return false
  }
  return sessionStorage.getItem(DEMO_SESSION_KEY) === '1'
}

export function getDemoSiteUrl(): string {
  const envUrl = (import.meta.env.VITE_SITE_URL as string | undefined)?.trim()
  if (envUrl) return envUrl
  return 'https://evidocs.douglaspaz.site/'
}

let state: DemoState = createInitialDemoState()

export function resetDemoState(): void {
  state = createInitialDemoState()
}

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

async function parseBody<T>(init?: RequestInit): Promise<T | null> {
  if (!init?.body || typeof init.body !== 'string') return null
  try {
    return JSON.parse(init.body) as T
  } catch {
    return null
  }
}

function atualizarConformidadeAposRevisao(doc: DocumentoResponse): void {
  const cnpj = doc.campos?.cnpj
  if (!cnpj) return
  const conf = state.conformidades[cnpj]
  if (!conf) return

  // Remove pendência ligada a este documento e devolve pontos em memória se aplicável
  const tinhaPendencia = conf.geral.pendencias.some((p) => p.documento === doc.id)
  conf.geral.pendencias = conf.geral.pendencias.filter((p) => p.documento !== doc.id)
  conf.geral.provisorio = conf.geral.pendencias.length > 0

  if (tinhaPendencia && conf.geral.score !== null) {
    const novoScore = Math.min(100, conf.geral.score + 8)
    conf.geral.score = novoScore
    conf.geral.score_bruto = novoScore
    conf.geral.classificacao = novoScore >= 85 ? 'Regular' : novoScore >= 65 ? 'Atenção' : 'Crítico'
  }
}

/**
 * Roteador in-memory para authFetch quando isDemoMode() === true.
 * Permite navegar em todas as telas e testar ações simples em memória sem tocar no backend.
 */
export async function demoFetch(rawPath: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method || 'GET').toUpperCase()
  const [pathname, queryString = ''] = rawPath.split('?')
  const params = new URLSearchParams(queryString)

  // Pequeno atraso natural para manter feedback visual de loading sem parecer travado
  await new Promise((r) => window.setTimeout(r, 80))

  // 1. Saúde e usuário demo
  if (pathname === '/health') return jsonResponse({ status: 'ok', demo: true })
  if (pathname === '/auth/me') return jsonResponse(DEMO_USUARIO)
  if (pathname === '/tipos') return jsonResponse(DEMO_TIPOS)

  // 2. Imagem real da página escaneada (/lotes/:loteId/paginas/:pagina/imagem)
  const imgMatch = pathname.match(/^\/lotes\/(\d+)\/paginas\/(\d+)\/imagem$/)
  if (imgMatch && method === 'GET') {
    const key = `${imgMatch[1]}:${imgMatch[2]}`
    const assetUrl = DEMO_PAGE_IMAGES[key] ?? '/demo/folha_ponto_scan.webp'
    const resp = await fetch(assetUrl, { signal: init.signal })
    if (!resp.ok) return new Response(null, { status: 404 })
    const blob = await resp.blob()
    return new Response(blob, {
      status: 200,
      headers: { 'Content-Type': blob.type || 'image/webp' },
    })
  }

  // 3. Documentos agrupados (GET /documentos)
  if (pathname === '/documentos' && method === 'GET') {
    const contratoParam = params.get('contrato_id')
    const falhouParam = params.get('falhou')
    let docs = [...state.documentos]
    if (contratoParam) {
      const cid = Number(contratoParam)
      docs = docs.filter((d) => d.contrato_id === cid)
    }
    if (falhouParam === 'true') {
      docs = docs.filter((d) => d.estado === 'erro')
    }
    const map = new Map<string, DocumentoResponse[]>()
    for (const d of docs) {
      const tipo = d.tipo || 'desconhecido'
      const lista = map.get(tipo) ?? []
      lista.push(d)
      map.set(tipo, lista)
    }
    const grupos = Array.from(map.entries()).map(([tipo, lista]) => ({
      tipo,
      total: lista.length,
      documentos: lista,
    }))
    const payload: DocumentosAgrupadosResponse = { grupos }
    return jsonResponse(payload)
  }

  // 4. Fila de revisão humana (GET /revisao)
  if (pathname === '/revisao' && method === 'GET') {
    const itens: RevisaoItemResponse[] = state.documentos
      .filter((d) => d.estado === 'em_revisao')
      .map((d) => ({
        id: d.id,
        lote_id: d.lote_id,
        tipo_sugerido: d.tipo,
        confianca: d.confianca,
        motivo: state.revisaoMotivos[d.id] ?? 'baixa_confianca',
        imagem_url: `/lotes/${d.lote_id}/paginas/${d.pagina_ini}/imagem`,
        pagina_ini: d.pagina_ini,
        pagina_fim: d.pagina_fim,
        campos: d.campos ?? {},
        pessoa: d.pessoa ?? null,
        nome_arquivo: d.nome_arquivo ?? `documento_${d.id}.pdf`,
        n_paginas: d.n_paginas ?? 1,
        processado_em: d.processado_em ?? new Date().toISOString(),
      }))
    return jsonResponse(itens)
  }

  // 5. Detalhe / Ações de um documento específico (/documentos/:id/...)
  const docMatch = pathname.match(/^\/documentos\/(\d+)(?:\/([a-z-]+))?$/)
  if (docMatch) {
    const docId = Number(docMatch[1])
    const sub = docMatch[2]
    const doc = state.documentos.find((d) => d.id === docId)

    if (!doc) return jsonResponse({ detail: 'Documento não encontrado na demo.' }, 404)

    if (!sub && method === 'GET') return jsonResponse(doc)

    if (!sub && method === 'DELETE') {
      state.documentos = state.documentos.filter((d) => d.id !== docId)
      return new Response(null, { status: 204 })
    }

    if (sub === 'analise-ponto' && method === 'GET') {
      const analise = state.analisesPonto[docId]
      if (!analise) return jsonResponse({ detail: 'Análise de ponto não disponível para este documento.' }, 404)
      return jsonResponse(analise)
    }

    if (sub === 'revisao' && method === 'POST') {
      const body = await parseBody<{ tipo?: string }>(init)
      const novoTipo = body?.tipo || doc.tipo || 'aso'
      doc.tipo_original = doc.tipo
      doc.tipo = novoTipo
      doc.estado = 'revisado'
      doc.confianca = 1
      atualizarConformidadeAposRevisao(doc)
      return jsonResponse({
        id: doc.id,
        estado: 'revisado',
        tipo: novoTipo,
        tipo_original: doc.tipo_original,
        revisor: DEMO_USUARIO.nome,
        revisado_em: new Date().toISOString(),
      })
    }

    if (sub === 'tipo' && method === 'PATCH') {
      const body = await parseBody<{ tipo?: string }>(init)
      if (body?.tipo) {
        doc.tipo_original = doc.tipo
        doc.tipo = body.tipo
      }
      return jsonResponse(doc)
    }

    if (sub === 'campos' && method === 'PUT') {
      const body = await parseBody<{ campos?: Record<string, string | null> }>(init)
      if (body?.campos) {
        const atual = { ...(doc.campos ?? {}) }
        for (const [k, v] of Object.entries(body.campos)) {
          if (v === null) delete atual[k]
          else atual[k] = v
        }
        doc.campos = atual
      }
      return jsonResponse(doc)
    }

    if (sub === 'download' && method === 'GET') {
      const key = `${doc.lote_id}:${doc.pagina_ini}`
      const assetUrl = DEMO_PAGE_IMAGES[key] ?? '/demo/folha_ponto_scan.webp'
      const resp = await fetch(assetUrl)
      const blob = await resp.blob()
      return new Response(blob, {
        status: 200,
        headers: {
          'Content-Type': blob.type || 'image/webp',
          'Content-Disposition': `attachment; filename="${(doc.nome_arquivo || `doc_${doc.id}`).replace(/\.pdf$/i, '.webp')}"`,
        },
      })
    }
  }

  // 6. Busca textual in-memory (GET /busca?q=...)
  if (pathname === '/busca' && method === 'GET') {
    const q = (params.get('q') || '').trim().toLowerCase()
    const limite = Number(params.get('limite') || '20')
    if (!q) return jsonResponse([])
    const resultados: SearchResult[] = []
    for (const doc of state.documentos) {
      const textoPag = doc.paginas[0]?.texto_ocr ?? ''
      const camposTexto = Object.values(doc.campos ?? {}).join(' ')
      const alvo = `${doc.nome_arquivo ?? ''} ${doc.pessoa ?? ''} ${doc.tipo ?? ''} ${camposTexto} ${textoPag}`.toLowerCase()
      if (alvo.includes(q)) {
        const idx = textoPag.toLowerCase().indexOf(q)
        const trecho =
          idx >= 0
            ? textoPag.slice(Math.max(0, idx - 40), idx + 120)
            : textoPag.slice(0, 140) || camposTexto.slice(0, 140)
        resultados.push({
          lote_id: doc.lote_id,
          pagina: doc.pagina_ini,
          trecho,
          documento_id: doc.id,
          tipo: doc.tipo,
          nome_arquivo: doc.nome_original ?? doc.nome_arquivo ?? '',
          nome_documento: doc.nome_arquivo ?? null,
          pessoa: doc.pessoa ?? null,
          pagina_ini: doc.pagina_ini,
          pagina_fim: doc.pagina_fim,
        })
      }
      if (resultados.length >= limite) break
    }
    return jsonResponse(resultados)
  }

  // 7. Empresas e Conformidade
  if (pathname === '/empresas' && method === 'GET') {
    return jsonResponse(buildCompaniesSummary(state))
  }

  const confMatch = pathname.match(/^\/empresas\/([^/]+)\/conformidade$/)
  if (confMatch && method === 'GET') {
    const cnpj = decodeURIComponent(confMatch[1])
    const conf = state.conformidades[cnpj]
    if (!conf) return jsonResponse({ detail: 'Empresa não encontrada na demo.' }, 404)
    return jsonResponse(conf)
  }

  // 8. Lotes (listagem, status e upload simulado em memória)
  if (pathname === '/lotes' && method === 'GET') {
    return jsonResponse({ itens: state.lotes, proximo_cursor: null })
  }

  if (pathname === '/lotes' && method === 'POST') {
    const novoLoteId = state.nextLoteId++
    const novoDocId = state.nextDocId++
    const agora = new Date().toISOString()
    DEMO_PAGE_IMAGES[`${novoLoteId}:1`] = '/demo/holerite_scan.webp'
    const novoDoc: DocumentoResponse = {
      id: novoDocId,
      lote_id: novoLoteId,
      ordem: 1,
      pagina_ini: 1,
      pagina_fim: 1,
      estado: 'classificado',
      tipo: 'holerite',
      confianca: 0.98,
      contrato_id: 1,
      pessoa: 'Exemplo Enviado na Demo',
      nome_arquivo: `demo_upload_${novoLoteId}.pdf`,
      nome_original: `demo_upload_${novoLoteId}.pdf`,
      n_paginas: 1,
      processado_em: agora,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        competencia: '11/2026',
        observacao: 'Processado em memória (modo demo)',
      },
      paginas: [
        {
          numero: 1,
          imagem_url: `/lotes/${novoLoteId}/paginas/1/imagem`,
          texto_ocr: 'Documento simulado em memória no modo demonstração do EviDocs.',
        },
      ],
    }
    state.documentos.unshift(novoDoc)
    state.lotes.unshift({
      id: novoLoteId,
      nome_arquivo: novoDoc.nome_original ?? 'upload_demo.pdf',
      estado: 'concluido',
      docs_pendentes: 0,
      contrato_id: 1,
      criado_em: agora,
      total_documentos: 1,
      em_revisao: 0,
      com_erro: 0,
    })
    return jsonResponse({ lote_id: novoLoteId, estado: 'concluido', existente: false, contrato_id: 1 }, 201)
  }

  const loteMatch = pathname.match(/^\/lotes\/(\d+)(?:\/([a-z-]+))?$/)
  if (loteMatch) {
    const loteId = Number(loteMatch[1])
    const sub = loteMatch[2]
    const resumo = state.lotes.find((l) => l.id === loteId)
    const docsDoLote = state.documentos.filter((d) => d.lote_id === loteId)
    const payload: LoteStatusResponse = {
      id: loteId,
      nome_arquivo: resumo?.nome_arquivo ?? `lote_${loteId}.pdf`,
      estado: 'concluido',
      docs_pendentes: 0,
      contrato_id: resumo?.contrato_id ?? 1,
      documentos: docsDoLote,
    }
    if (sub === 'eventos') {
      const sse = `data: ${JSON.stringify(payload)}\n\n`
      return new Response(sse, { status: 200, headers: { 'Content-Type': 'text/event-stream' } })
    }
    return jsonResponse(payload)
  }

  // 9. Organizações, Contratos, Perfis de Jornada, Equipe e Convites
  if (pathname === '/tomadores' && method === 'GET') return jsonResponse(state.tomadores)
  if (pathname === '/prestadores' && method === 'GET') return jsonResponse(state.prestadores)
  if (pathname === '/contratos' && method === 'GET') return jsonResponse(state.contratos)
  if (pathname === '/usuarios' && method === 'GET') return jsonResponse(state.usuarios)
  if (pathname === '/convites' && method === 'GET') return jsonResponse(state.convites)

  if (pathname === '/perfis-jornada' && method === 'GET') {
    const resumos: PerfilJornadaResumo[] = state.perfisJornada.map((p) => ({
      perfil: p.perfil,
      nome: p.nome,
      sindicato: p.sindicato,
      vigencia_inicio: p.vigencia_inicio,
      vigencia_fim: p.vigencia_fim,
      vigente: p.vigente,
      geral: p.geral,
      prestador_id: p.prestador_id,
      editavel: p.editavel,
      padrao: p.padrao,
      parametros_proprios: p.proprios.length,
      contratos: state.contratos.filter((c) => c.perfil_jornada === p.perfil).length,
    }))
    return jsonResponse(resumos)
  }

  const perfilMatch = pathname.match(/^\/perfis-jornada\/([^/]+)$/)
  if (perfilMatch && method === 'GET') {
    const slug = decodeURIComponent(perfilMatch[1])
    const found = state.perfisJornada.find((p) => p.perfil === slug)
    if (!found) return jsonResponse({ detail: 'Perfil de jornada não encontrado.' }, 404)
    return jsonResponse(found)
  }

  if (pathname === '/perfis-jornada' && method === 'POST') {
    const body = await parseBody<{
      nome?: string
      sindicato?: string | null
      vigencia_inicio?: string | null
      vigencia_fim?: string | null
      geral?: boolean
      prestador_id?: number | null
    }>(init)
    const nome = (body?.nome || 'Nova convenção demo').trim()
    const slug =
      nome
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '') || `perfil_${Date.now()}`
    const padrao = state.perfisJornada.find((p) => p.padrao) ?? state.perfisJornada[0]
    const novo = {
      perfil: slug,
      nome,
      sindicato: body?.sindicato ?? null,
      vigencia_inicio: body?.vigencia_inicio ?? null,
      vigencia_fim: body?.vigencia_fim ?? null,
      vigente: true,
      geral: body?.geral ?? true,
      prestador_id: body?.prestador_id ?? null,
      editavel: true,
      padrao: false,
      proprios: [],
      efetivo: { ...padrao.efetivo },
    }
    state.perfisJornada.push(novo)
    return jsonResponse(novo, 201)
  }

  if (perfilMatch && method === 'PUT') {
    const slug = decodeURIComponent(perfilMatch[1])
    const found = state.perfisJornada.find((p) => p.perfil === slug)
    if (!found) return jsonResponse({ detail: 'Perfil de jornada não encontrado.' }, 404)
    const body = await parseBody<{
      nome?: string
      sindicato?: string | null
      vigencia_inicio?: string | null
      vigencia_fim?: string | null
      geral?: boolean
      prestador_id?: number | null
      parametros?: { parametro: string; valor: number; base_legal: string; vigente_desde: string | null }[]
    }>(init)
    if (body?.nome !== undefined) found.nome = body.nome
    if (body?.sindicato !== undefined) found.sindicato = body.sindicato
    if (body?.vigencia_inicio !== undefined) found.vigencia_inicio = body.vigencia_inicio
    if (body?.vigencia_fim !== undefined) found.vigencia_fim = body.vigencia_fim
    if (body?.geral !== undefined) found.geral = body.geral
    if (body?.prestador_id !== undefined) found.prestador_id = body.prestador_id
    if (body?.parametros) {
      const padrao = state.perfisJornada.find((p) => p.padrao) ?? state.perfisJornada[0]
      found.proprios = body.parametros.map((p) => ({
        ...p,
        unidade: p.parametro.endsWith('_pct') ? '%' : 'min',
      }))
      const novoEfetivo = { ...padrao.efetivo }
      for (const p of body.parametros) {
        novoEfetivo[p.parametro] = { valor: p.valor, base_legal: p.base_legal }
      }
      found.efetivo = novoEfetivo
    }
    return jsonResponse(found)
  }

  const contratoPerfilMatch = pathname.match(/^\/contratos\/(\d+)\/perfil-jornada$/)
  if (contratoPerfilMatch && method === 'PUT') {
    const cid = Number(contratoPerfilMatch[1])
    const body = await parseBody<{ perfil?: string }>(init)
    const contrato = state.contratos.find((c) => c.id === cid)
    if (!contrato) return jsonResponse({ detail: 'Contrato não encontrado.' }, 404)
    if (body?.perfil) {
      const perfilObj = state.perfisJornada.find((p) => p.perfil === body.perfil)
      contrato.perfil_jornada = body.perfil
      contrato.perfil_jornada_nome = perfilObj?.nome ?? body.perfil
    }
    return jsonResponse(contrato)
  }

  // Qualquer outra ação de escrita administrativa no modo demo responde educadamente sem falhar
  if (method !== 'GET') {
    return jsonResponse(
      { detail: 'No modo demonstração, alterações administrativas não são persistidas em servidor.' },
      400,
    )
  }

  return jsonResponse({ detail: `Rota não simulada na demo: ${pathname}` }, 404)
}

