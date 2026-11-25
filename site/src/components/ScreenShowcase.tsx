import React, { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Maximize2, X } from 'lucide-react'

interface TelaItem {
  src: string
  rota: string
  alt: string
  legenda: string
}

interface GrupoTela {
  id: number
  etiqueta: string
  titulo: string
  curto: string
  telas: TelaItem[]
}

const GRUPOS: GrupoTela[] = [
  {
    id: 1,
    etiqueta: 'NA TELA · 1 DE 3',
    titulo: 'Separa e classifica sozinho.',
    curto: '1. Separa e classifica',
    telas: [
      {
        src: '/screens/image-4-1.png',
        rota: 'evidocs / documentos',
        alt: 'Tela Documentos do EviDocs mostrando 11 documentos classificados automaticamente pela IA em 7 tipos documentais',
        legenda: 'Um PDF de 12 páginas virou 10 documentos, separados e classificados sem ninguém revisar.',
      },
      {
        src: '/screens/image-4-2.png',
        rota: 'evidocs / folha-de-ponto',
        alt: 'Lista de folhas de ponto com CNPJ, competência, matrícula e empresa extraídos automaticamente',
        legenda: 'Campos extraídos de cada documento: CNPJ, competência, matrícula e empresa.',
      },
    ],
  },
  {
    id: 2,
    etiqueta: 'NA TELA · 2 DE 3',
    titulo: 'Audita o ponto pela lei.',
    curto: '2. Audita o ponto',
    telas: [
      {
        src: '/screens/image-5-1.png',
        rota: 'evidocs / auditoria-ponto',
        alt: 'Modal de auditoria de ponto mostrando risco alto 100%, 4 dimensões avaliadas, divergências com artigos da CLT e a folha original ao lado',
        legenda: 'Risco alto: horas extras acima do limite em 21 dias, com o artigo da CLT e a folha original ao lado.',
      },
      {
        src: '/screens/image-5-2.png',
        rota: 'evidocs / convencoes-coletivas',
        alt: 'Tabela de perfil de jornada por contrato com convenção coletiva e linha do tempo da EC 141/2026',
        legenda: 'Perfil por contrato: a convenção coletiva muda o limite, e a EC 141 já está na linha do tempo.',
      },
    ],
  },
  {
    id: 3,
    etiqueta: 'NA TELA · 3 DE 3',
    titulo: 'Dá nota a cada terceirizada.',
    curto: '3. Nota de conformidade',
    telas: [
      {
        src: '/screens/image-6-1.jpeg',
        rota: 'evidocs / conformidade',
        alt: 'Tabela Conformidade por Empresa com notas de 0 a 100 e faixas Regular e Crítico',
        legenda: 'Conformidade por empresa: de 0 a 100, com faixas Regular, Atenção e Crítico.',
      },
      {
        src: '/screens/image-6-2.png',
        rota: 'evidocs / avaliacao-documental',
        alt: 'Detalhe da avaliação documental mostrando nota 92/100 e a divergência cadastral a corrigir',
        legenda: 'O porquê da nota: 92 de 100, com a divergência que falta corrigir.',
      },
    ],
  },
]

const TODAS_TELAS = GRUPOS.flatMap((g) => g.telas)

export const ScreenShowcase: React.FC = () => {
  const [ativo, setAtivo] = useState(1)
  const [zoomIdx, setZoomIdx] = useState<number | null>(null)

  useEffect(() => {
    if (zoomIdx === null) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setZoomIdx(null)
      if (e.key === 'ArrowRight') setZoomIdx((i) => (i === null ? null : (i + 1) % TODAS_TELAS.length))
      if (e.key === 'ArrowLeft') setZoomIdx((i) => (i === null ? null : (i - 1 + TODAS_TELAS.length) % TODAS_TELAS.length))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [zoomIdx])

  const grupo = GRUPOS.find((g) => g.id === ativo) ?? GRUPOS[0]
  const zoomTela = zoomIdx !== null ? TODAS_TELAS[zoomIdx] : null

  return (
    <div className="space-y-10">
      {/* Cabeçalho + seletor segmentado */}
      <div className="flex flex-col items-start gap-6">
        <div className="space-y-2">
          <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
            {grupo.etiqueta}
          </div>
          <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight text-[#2d0a33] dark:text-white">
            {grupo.titulo}
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:inline-flex sm:flex-nowrap w-full sm:w-auto gap-1 p-1.5 rounded-2xl border border-[#e6dfec] dark:border-[#2e1e38] bg-white/85 dark:bg-[#1a1020]/90 shadow-sm">
          {GRUPOS.map((g) => {
            const selecionado = g.id === ativo
            return (
              <button
                key={g.id}
                type="button"
                onClick={() => setAtivo(g.id)}
                className={`px-4 py-2 rounded-xl text-xs sm:text-sm font-semibold whitespace-nowrap text-left sm:text-center transition-all duration-200 cursor-pointer ${
                  selecionado
                    ? 'bg-gradient-to-r from-[#9333ea] to-[#7e22ce] text-white shadow-md shadow-[#9333ea]/25'
                    : 'text-[#6e6378] dark:text-[#b2a4bc] hover:text-[#2d0a33] dark:hover:text-white'
                }`}
              >
                {g.curto}
              </button>
            )
          })}
        </div>
      </div>

      {/* 2 capturas reais em moldura de janela do produto */}
      <div key={grupo.id} className="grid lg:grid-cols-2 gap-7 animate-[fadeSlide_0.38s_ease-out]">
        {grupo.telas.map((tela) => {
          const globalIndex = TODAS_TELAS.findIndex((t) => t.src === tela.src)
          return (
            <figure
              key={tela.src}
              className="group relative rounded-2xl p-[1px] bg-gradient-to-b from-[#e6dfec] via-[#e6dfec] to-[#e6dfec] dark:from-[#3a2548] dark:via-[#281933] dark:to-[#22152b] hover:from-[#ff79e7]/60 hover:via-[#bd79ff]/50 hover:to-[#5ddfff]/60 transition-all duration-300 shadow-xl shadow-black/[0.04] dark:shadow-black/35"
            >
              <div className="rounded-[15px] bg-white dark:bg-[#170e1d] overflow-hidden h-full flex flex-col">
                {/* Barra superior estilo janela */}
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-[#ece8ef] dark:border-[#27192f] bg-[#f8f4fa] dark:bg-[#130b16]">
                  <div className="flex items-center gap-1.5" aria-hidden="true">
                    <span className="w-2.5 h-2.5 rounded-full bg-[#ff79e7]/65" />
                    <span className="w-2.5 h-2.5 rounded-full bg-[#bd79ff]/65" />
                    <span className="w-2.5 h-2.5 rounded-full bg-[#5ddfff]/65" />
                  </div>
                  <span className="text-[11px] font-mono text-[#7a6d85] dark:text-[#9c8ea6]">{tela.rota}</span>
                  <span className="w-9" aria-hidden="true" />
                </div>

                {/* Imagem clicável */}
                <button
                  type="button"
                  onClick={() => setZoomIdx(globalIndex)}
                  className="relative block w-full overflow-hidden bg-[#140c17] cursor-zoom-in focus:outline-none"
                  aria-label={`Ampliar captura: ${tela.legenda}`}
                >
                  <img
                    src={tela.src}
                    alt={tela.alt}
                    loading="lazy"
                    className="w-full aspect-[16/10] object-cover object-top transition-transform duration-500 ease-out group-hover:scale-[1.025]"
                  />
                  <span className="absolute right-3 bottom-3 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-[#140c17]/85 backdrop-blur-md text-white border border-white/15 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Maximize2 className="w-3.5 h-3.5" /> Ampliar tela
                  </span>
                </button>

                <figcaption className="px-5 py-4 text-sm text-[#4c3e57] dark:text-[#d3c7dc] leading-relaxed mt-auto">
                  {tela.legenda}
                </figcaption>
              </div>
            </figure>
          )
        })}
      </div>

      {/* Lightbox com navegação por setas */}
      {zoomTela && zoomIdx !== null && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => setZoomIdx(null)}
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 sm:p-8"
        >
          <div
            onClick={(e) => e.stopPropagation()}
            className="relative max-w-5xl w-full rounded-2xl border border-white/15 bg-[#140c17] overflow-hidden shadow-2xl"
          >
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
              <span className="text-xs font-mono text-[#b7a8c2]">
                {zoomTela.rota} · {zoomIdx + 1}/{TODAS_TELAS.length}
              </span>
              <button
                type="button"
                onClick={() => setZoomIdx(null)}
                aria-label="Fechar imagem ampliada"
                className="p-1.5 rounded-lg text-[#d3c7dc] hover:bg-white/10 hover:text-white cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="relative bg-[#100813]">
              <img
                src={zoomTela.src}
                alt={zoomTela.alt}
                className="w-full max-h-[75vh] object-contain mx-auto"
              />
              <button
                type="button"
                onClick={() => setZoomIdx((zoomIdx - 1 + TODAS_TELAS.length) % TODAS_TELAS.length)}
                aria-label="Tela anterior"
                className="absolute left-3 top-1/2 -translate-y-1/2 p-2.5 rounded-full bg-black/70 text-white hover:bg-black border border-white/15 cursor-pointer"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                type="button"
                onClick={() => setZoomIdx((zoomIdx + 1) % TODAS_TELAS.length)}
                aria-label="Próxima tela"
                className="absolute right-3 top-1/2 -translate-y-1/2 p-2.5 rounded-full bg-black/70 text-white hover:bg-black border border-white/15 cursor-pointer"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>

            <div className="px-5 py-4 text-sm text-[#e9dff0] border-t border-white/10">{zoomTela.legenda}</div>
          </div>
        </div>
      )}
    </div>
  )
}
