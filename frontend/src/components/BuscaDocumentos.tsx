import React, { useCallback, useEffect, useId, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { FileText, Loader2, Search, X } from 'lucide-react'
import { apiService } from '../services/api'
import type { TipoDocumentoResponse } from '../services/api'
import type { DetailedDocument } from '../types'
import { DocumentPreviewModal } from './DocumentPreviewModal'
import { rotuloTipoDocumental } from '../utils/rotulos'
import {
  agruparResultados,
  documentoParaVisualizador,
  ESPERA_BUSCA_MS,
  MIN_CARACTERES_BUSCA,
  type GrupoBusca,
} from '../utils/busca'

interface BuscaDocumentosProps {
  /** `barra`: campo no cabeçalho, com os resultados num painel flutuante. `menu`: dentro do menu do celular. */
  variante: 'barra' | 'menu'
  empresaPropria?: boolean
}

type Situacao = 'ocioso' | 'buscando' | 'pronto' | 'erro'

interface Aberto {
  doc: DetailedDocument
  pagina: number
}

// Nomes dos tipos (GET /tipos), buscados uma vez só.
let nomesTipos: Record<string, string> | null = null
const carregarNomesTipos = async (): Promise<Record<string, string>> => {
  if (nomesTipos) return nomesTipos
  try {
    const tipos: TipoDocumentoResponse[] = await apiService.getTipos()
    nomesTipos = Object.fromEntries(tipos.map((t) => [t.slug, t.nome]))
    return nomesTipos
  } catch {
    return {}
  }
}

const FOCO = 'focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea]'

export const BuscaDocumentos: React.FC<BuscaDocumentosProps> = ({ variante, empresaPropria = false }) => {
  const idBase = useId()
  const [texto, setTexto] = useState('')
  const [consulta, setConsulta] = useState('')
  const [situacao, setSituacao] = useState<Situacao>('ocioso')
  const [grupos, setGrupos] = useState<GrupoBusca[]>([])
  const [nomes, setNomes] = useState<Record<string, string>>({})
  const [painelAberto, setPainelAberto] = useState(false)
  const [abrindo, setAbrindo] = useState<string | null>(null)
  const [erroAbrir, setErroAbrir] = useState(false)
  const [aberto, setAberto] = useState<Aberto | null>(null)

  const raizRef = useRef<HTMLDivElement>(null)
  const campoRef = useRef<HTMLInputElement>(null)
  const painelRef = useRef<HTMLDivElement>(null)
  const pedidoRef = useRef(0)
  const temporizadorRef = useRef<number | undefined>(undefined)

  const executar = useCallback(async (termo: string) => {
    const pedido = ++pedidoRef.current
    setConsulta(termo)
    setSituacao('buscando')
    setErroAbrir(false)
    setPainelAberto(true)
    try {
      const [resultados, mapa] = await Promise.all([apiService.search(termo, 30), carregarNomesTipos()])
      if (pedido !== pedidoRef.current) return
      setNomes(mapa)
      setGrupos(agruparResultados(resultados))
      setSituacao('pronto')
    } catch {
      if (pedido !== pedidoRef.current) return
      setGrupos([])
      setSituacao('erro')
    }
  }, [])

  // Espera ~300 ms depois da última tecla; menos de 2 caracteres não busca.
  useEffect(() => {
    const termo = texto.trim()
    if (termo.length < MIN_CARACTERES_BUSCA) {
      pedidoRef.current++
      return
    }
    temporizadorRef.current = window.setTimeout(() => void executar(termo), ESPERA_BUSCA_MS)
    return () => window.clearTimeout(temporizadorRef.current)
  }, [texto, executar])

  // Painel flutuante: clique fora fecha.
  useEffect(() => {
    if (!painelAberto || variante !== 'barra') return
    const aoClicarFora = (e: MouseEvent) => {
      if (raizRef.current && !raizRef.current.contains(e.target as Node)) setPainelAberto(false)
    }
    document.addEventListener('mousedown', aoClicarFora)
    return () => document.removeEventListener('mousedown', aoClicarFora)
  }, [painelAberto, variante])

  const curto = texto.trim().length < MIN_CARACTERES_BUSCA
  const textoBuscado = consulta === texto.trim()

  const limpar = () => {
    window.clearTimeout(temporizadorRef.current)
    pedidoRef.current++
    setTexto('')
    setConsulta('')
    setGrupos([])
    setSituacao('ocioso')
    setPainelAberto(false)
    campoRef.current?.focus()
  }

  const botoesResultado = (): HTMLButtonElement[] =>
    Array.from(painelRef.current?.querySelectorAll<HTMLButtonElement>('button[data-resultado]') ?? [])

  const aoTeclarCampo = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      const termo = texto.trim()
      if (termo.length >= MIN_CARACTERES_BUSCA) {
        window.clearTimeout(temporizadorRef.current)
        void executar(termo)
      } else {
        setPainelAberto(true)
      }
    } else if (e.key === 'ArrowDown') {
      const botoes = botoesResultado()
      if (botoes.length > 0) {
        e.preventDefault()
        botoes[0].focus()
      }
    } else if (e.key === 'Escape' && painelAberto) {
      e.stopPropagation()
      setPainelAberto(false)
    }
  }

  const aoTeclarPainel = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      setPainelAberto(false)
      campoRef.current?.focus()
      return
    }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    const botoes = botoesResultado()
    const indice = botoes.indexOf(document.activeElement as HTMLButtonElement)
    if (indice < 0) return
    e.preventDefault()
    if (e.key === 'ArrowDown') botoes[Math.min(indice + 1, botoes.length - 1)].focus()
    else if (indice === 0) campoRef.current?.focus()
    else botoes[indice - 1].focus()
  }

  const abrirResultado = async (grupo: GrupoBusca, pagina: number) => {
    if (grupo.documentoId == null) return
    setAbrindo(`${grupo.chave}:${pagina}`)
    setErroAbrir(false)
    try {
      const detalhe = await apiService.getDocumentDetails(grupo.documentoId)
      setAberto({ doc: documentoParaVisualizador(detalhe), pagina })
    } catch {
      setErroAbrir(true)
    } finally {
      setAbrindo(null)
    }
  }

  const idPainel = `${idBase}-resultados`
  const idStatus = `${idBase}-status`
  const mostrarPainel = painelAberto && texto.trim() !== ''

  const painel = (
    <div
      ref={painelRef}
      id={idPainel}
      onKeyDown={aoTeclarPainel}
      className={
        variante === 'barra'
          ? 'absolute right-0 top-[calc(100%+8px)] w-[min(30rem,calc(100vw-2rem))] max-h-[70vh] overflow-y-auto rounded-xl border border-[#e6dfec] dark:border-[#2a1d32] bg-white dark:bg-[#140d18] shadow-xl p-2 z-50'
          : 'mt-1 max-h-[55vh] overflow-y-auto'
      }
    >
      <p id={idStatus} role="status" aria-live="polite" className="px-2 py-1.5 text-sm text-[#6e6378] dark:text-[#a093a8]">
        {curto && 'Digite pelo menos 2 letras para buscar.'}
        {!curto && situacao === 'buscando' && (
          <span className="inline-flex items-center gap-2">
            <Loader2 className="w-4 h-4 animate-spin" aria-hidden="true" />
            Buscando...
          </span>
        )}
        {!curto && situacao === 'pronto' && textoBuscado && grupos.length === 0 && (
          <>Nenhum resultado para “{consulta}”. Tente outra palavra.</>
        )}
        {!curto && situacao === 'pronto' && textoBuscado && grupos.length > 0 && (
          <>{grupos.length === 1 ? '1 documento encontrado' : `${grupos.length} documentos encontrados`}</>
        )}
        {!curto && situacao === 'erro' && 'Não foi possível buscar agora. Confira sua conexão e tente de novo.'}
        {erroAbrir && ' Não foi possível abrir o documento. Tente de novo.'}
      </p>

      {!curto && situacao === 'erro' && (
        <button
          type="button"
          onClick={() => void executar(texto.trim())}
          className={`mx-2 mb-1 px-3 py-1.5 rounded-lg text-sm font-medium bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9] cursor-pointer ${FOCO}`}
        >
          Tentar de novo
        </button>
      )}

      {!curto &&
        situacao !== 'erro' &&
        grupos.map((grupo) => (
          <section key={grupo.chave} aria-label={grupo.nomeArquivo} className="mt-1 first:mt-0">
            <div className="px-2 pt-2 pb-1 flex items-center gap-2 min-w-0">
              <FileText className="w-4 h-4 shrink-0 text-[#9333ea] dark:text-[#d67bf3]" aria-hidden="true" />
              <h3 className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc] truncate">{grupo.nomeArquivo}</h3>
              <span className="shrink-0 text-xs text-[#6e6378] dark:text-[#a093a8]">
                {rotuloTipoDocumental(grupo.tipo, nomes)}
              </span>
            </div>
            <ul>
              {grupo.itens.map((item) => {
                const chave = `${grupo.chave}:${item.pagina}`
                const conteudo = (
                  <>
                    <span className="block text-xs font-semibold text-[#6e6378] dark:text-[#a093a8]">
                      Página {item.pagina}
                      {abrindo === chave && ' · abrindo...'}
                    </span>
                    <span className="block text-sm text-[#2d0a33] dark:text-[#f5edf9] break-words">
                      {item.partes.map((parte, i) =>
                        parte.destaque ? (
                          <mark
                            key={i}
                            className="bg-[#f4e8f7] text-[#5c1363] dark:bg-[#4a1d56] dark:text-[#f9d7fc] font-semibold rounded-sm px-0.5"
                          >
                            {parte.texto}
                          </mark>
                        ) : (
                          <React.Fragment key={i}>{parte.texto}</React.Fragment>
                        ),
                      )}
                    </span>
                  </>
                )
                return (
                  <li key={chave}>
                    {grupo.documentoId != null ? (
                      <button
                        type="button"
                        data-resultado
                        disabled={abrindo !== null}
                        onClick={() => void abrirResultado(grupo, item.pagina)}
                        className={`w-full text-left px-2 py-2 rounded-lg hover:bg-[#f3edf6] dark:hover:bg-[#281831] cursor-pointer disabled:cursor-wait ${FOCO}`}
                      >
                        {conteudo}
                      </button>
                    ) : (
                      <div className="px-2 py-2">{conteudo}</div>
                    )}
                  </li>
                )
              })}
            </ul>
          </section>
        ))}
    </div>
  )

  return (
    <div ref={raizRef} className={variante === 'barra' ? 'relative' : 'p-1.5'}>
      <form role="search" aria-label="Buscar nos documentos" onSubmit={(e) => e.preventDefault()} className="relative">
        <label htmlFor={`${idBase}-campo`} className="sr-only">
          Buscar nos documentos
        </label>
        <Search
          className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#8f8298] dark:text-[#83748d] pointer-events-none"
          aria-hidden="true"
        />
        <input
          ref={campoRef}
          id={`${idBase}-campo`}
          type="search"
          autoComplete="off"
          placeholder="Buscar nos documentos"
          value={texto}
          onChange={(e) => {
            setTexto(e.target.value)
            setPainelAberto(true)
          }}
          onFocus={() => {
            if (texto.trim() !== '') setPainelAberto(true)
          }}
          onKeyDown={aoTeclarCampo}
          aria-controls={mostrarPainel ? idPainel : undefined}
          aria-describedby={mostrarPainel ? idStatus : undefined}
          className={`w-full ${variante === 'barra' ? 'sm:w-44 lg:w-64' : ''} pl-9 pr-9 py-1.5 text-sm rounded-lg bg-[#f8f6fa] dark:bg-[#1d1222] border border-[#e5dfec] dark:border-[#311f3d] text-[#2d0a33] dark:text-[#f5edf9] placeholder-[#6e6378] dark:placeholder-[#a093a8] [&::-webkit-search-cancel-button]:hidden ${FOCO}`}
        />
        {texto !== '' && (
          <button
            type="button"
            onClick={limpar}
            aria-label="Limpar busca"
            className={`absolute right-1.5 top-1/2 -translate-y-1/2 p-1 rounded-md text-[#6e6378] dark:text-[#a093a8] hover:bg-[#f3edf6] dark:hover:bg-[#281831] cursor-pointer ${FOCO}`}
          >
            <X className="w-4 h-4" aria-hidden="true" />
          </button>
        )}
      </form>

      {mostrarPainel && painel}

      {aberto &&
        createPortal(
          <div data-visualizador-busca>
            <DocumentPreviewModal
              doc={aberto.doc}
              paginaInicial={aberto.pagina}
              empresaPropria={empresaPropria}
              onClose={() => setAberto(null)}
            />
          </div>,
          document.body,
        )}
    </div>
  )
}
