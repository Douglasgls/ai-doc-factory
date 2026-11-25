import React, { useEffect, useState } from 'react'
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  Award,
  Clock,
  FileStack,
  Moon,
  Scale,
  ScanText,
  Scissors,
  ShieldCheck,
  Sun,
  Tags,
  UserCheck,
} from 'lucide-react'
import { EviDocsBrand } from './components/EviDocsBrand'
import { CountUp, Reveal } from './components/Reveal'
import { ScreenShowcase } from './components/ScreenShowcase'

const NAV_LINKS = [
  { path: '/problema', id: 'problema', label: 'Problema' },
  { path: '/solucao', id: 'solucao', label: 'Solução' },
  { path: '/na-tela', id: 'na-tela', label: 'Na tela' },
  { path: '/resultados', id: 'resultados', label: 'Resultados' },
  { path: '/negocio', id: 'negocio', label: 'Negócio' },
  { path: '/confianca', id: 'confianca', label: 'Confiança' },
]

const DEMO_URL = (import.meta.env.VITE_DEMO_URL || 'http://localhost:5174/?demo=1').trim()

const PATH_TO_ID: Record<string, string> = Object.fromEntries(NAV_LINKS.map((l) => [l.path, l.id]))

const DORES = [
  {
    num: '01',
    icone: FileStack,
    titulo: 'Pilhas de PDF',
    texto: 'Todo mês chegam lotes escaneados com ASO, holerite, folha de ponto e contrato misturados.',
  },
  {
    num: '02',
    icone: UserCheck,
    titulo: 'Conferência à mão',
    texto: 'Alguém separa página por página e confere documento por documento.',
  },
  {
    num: '03',
    icone: Clock,
    titulo: 'Ponto sem auditoria',
    texto: 'A folha de ponto quase nunca é olhada com calma. É aí que mora o passivo.',
  },
]

const ETAPAS_PIPELINE = [
  { num: 1, icone: ScanText, titulo: 'OCR', detalhe: 'Texto pesquisável de cada página' },
  { num: 2, icone: Scissors, titulo: 'Separação', detalhe: 'Onde começa e termina cada documento' },
  { num: 3, icone: Tags, titulo: 'Classificação', detalhe: 'Entre 7 tipos de documento' },
  { num: 4, icone: Clock, titulo: 'Auditoria do ponto', detalhe: 'CLT, Portaria 671 e EC 141' },
  { num: 5, icone: Award, titulo: 'Conformidade', detalhe: 'Nota de 0 a 100 por terceirizada' },
]

const CUSTOS = [
  { item: 'Documento comum', ate2026: 'US$ 0,004', de2027: 'US$ 0,008' },
  { item: 'Folha de ponto', ate2026: 'US$ 0,021', de2027: 'US$ 0,043' },
  { item: '1.000 documentos, 20% de ponto', ate2026: 'US$ 7,40', de2027: 'US$ 15' },
]

const PILARES_CONFIANCA = [
  {
    num: '01',
    icone: Scale,
    texto: 'Cada desconto mostra o artigo da lei e a evidência.',
  },
  {
    num: '02',
    icone: Clock,
    texto: 'EC 141 já implementada: 42 h a partir de 16/12/2026 e 40 h a partir de 16/12/2027.',
  },
  {
    num: '03',
    icone: ShieldCheck,
    texto: 'Convenção coletiva vira um perfil de jornada por contrato.',
  },
]

export const App: React.FC = () => {
  const [isDark, setIsDark] = useState(false)
  const [etapaAtiva, setEtapaAtiva] = useState(1)
  const [progressoScroll, setProgressoScroll] = useState(0)
  const [rotaAtiva, setRotaAtiva] = useState(() => window.location.pathname || '/')

  useEffect(() => {
    const root = document.documentElement
    if (isDark) root.classList.add('dark')
    else root.classList.remove('dark')
  }, [isDark])

  const rolarParaRota = (path: string, behavior: ScrollBehavior = 'smooth') => {
    if (path === '/' || !PATH_TO_ID[path]) {
      window.scrollTo({ top: 0, behavior })
      return
    }
    const alvo = document.getElementById(PATH_TO_ID[path])
    alvo?.scrollIntoView({ behavior, block: 'start' })
  }

  const navegarPara = (path: string, e?: React.MouseEvent) => {
    e?.preventDefault()
    if (window.location.pathname !== path) {
      window.history.pushState({}, '', path)
    }
    setRotaAtiva(path)
    rolarParaRota(path, 'smooth')
  }

  // Navegação SPA inicial e botões Voltar/Avançar do navegador (sem # na URL)
  useEffect(() => {
    const inicial = window.location.pathname
    if (inicial && inicial !== '/') {
      window.requestAnimationFrame(() => rolarParaRota(inicial, 'auto'))
    }
    const onPopState = () => {
      const atual = window.location.pathname || '/'
      setRotaAtiva(atual)
      rolarParaRota(atual, 'smooth')
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  // Destaca a seção ativa na barra ao rolar
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const link = NAV_LINKS.find((l) => l.id === entry.target.id)
            if (link) setRotaAtiva(link.path)
          }
        }
      },
      { rootMargin: '-35% 0px -55% 0px' },
    )
    for (const l of NAV_LINKS) {
      const el = document.getElementById(l.id)
      if (el) observer.observe(el)
    }
    return () => observer.disconnect()
  }, [])

  // Barra fina de progresso de leitura no topo
  useEffect(() => {
    const onScroll = () => {
      const altura = document.documentElement.scrollHeight - window.innerHeight
      setProgressoScroll(altura > 0 ? Math.min(100, (window.scrollY / altura) * 100) : 0)
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    onScroll()
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Pulso fluido percorrendo os 5 passos da solução
  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => {
      setEtapaAtiva((n) => (n >= 5 ? 1 : n + 1))
    }, 2100)
    return () => window.clearInterval(id)
  }, [])

  return (
    <div id="topo" className="min-h-screen bg-[#fbf9fc] dark:bg-[#140c17] text-[#2d0a33] dark:text-[#f5eff8] transition-colors overflow-x-clip">
      {/* Aurora suave no topo */}
      <div
        aria-hidden="true"
        className="aurora-glow pointer-events-none fixed inset-x-0 top-0 h-[520px] z-0"
        style={{
          background:
            'radial-gradient(50% 48% at 20% 0%, rgba(255, 121, 231, 0.17), transparent 72%), radial-gradient(48% 45% at 80% 0%, rgba(93, 223, 255, 0.15), transparent 72%), radial-gradient(40% 35% at 50% 10%, rgba(147, 51, 234, 0.14), transparent 75%)',
        }}
      />

      {/* Navbar minimalista + linha de progresso */}
      <header className="sticky top-0 z-40 border-b border-[#ece8ef]/80 dark:border-[#27192f]/90 bg-white/80 dark:bg-[#140c17]/80 backdrop-blur-xl">
        <div className="max-w-5xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-between gap-4">
          <a href="/" onClick={(e) => navegarPara('/', e)} className="focus:outline-none">
            <EviDocsBrand sizeClass="text-2xl" />
          </a>

          <nav aria-label="Navegação" className="hidden md:flex items-center gap-1">
            {NAV_LINKS.map((l) => {
              const ativo = rotaAtiva === l.path
              return (
                <a
                  key={l.path}
                  href={l.path}
                  onClick={(e) => navegarPara(l.path, e)}
                  aria-current={ativo ? 'page' : undefined}
                  className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    ativo
                      ? 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#2d1638] dark:text-[#f38df9]'
                      : 'text-[#6e6378] dark:text-[#a89ab3] hover:text-[#2d0a33] dark:hover:text-white hover:bg-[#f4e8f7]/60 dark:hover:bg-[#24152d]'
                  }`}
                >
                  {l.label}
                </a>
              )
            })}
          </nav>

          <div className="flex items-center gap-2">
            <a
              href={DEMO_URL}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-xl text-xs sm:text-sm font-semibold bg-gradient-to-r from-[#9333ea] to-[#7e22ce] hover:brightness-110 text-white shadow-sm shadow-[#9333ea]/25 transition-all"
            >
              Demo
              <ArrowRight className="w-3.5 h-3.5" />
            </a>

            <button
              type="button"
              onClick={() => setIsDark((d) => !d)}
              aria-label="Alternar tema"
              title={isDark ? 'Modo claro' : 'Modo escuro'}
              className="p-2 rounded-xl border border-transparent hover:border-[#e6dfec] dark:hover:border-[#2e1e38] text-[#6e6378] dark:text-[#d3c7dc] hover:bg-[#f3edf6] dark:hover:bg-[#23142c] transition-all cursor-pointer"
            >
              {isDark ? <Sun className="w-5 h-5 text-amber-300" /> : <Moon className="w-5 h-5 text-[#3e0b48]" />}
            </button>
          </div>
        </div>

        {/* Progresso de leitura com o gradiente oficial EviDocs */}
        <div className="h-[2px] w-full bg-transparent">
          <div
            className="h-full bg-gradient-to-r from-[#ff79e7] via-[#bd79ff] to-[#5ddfff] transition-[width] duration-150 ease-out"
            style={{ width: `${progressoScroll}%` }}
          />
        </div>
      </header>

      <main className="relative z-10">
        {/* 1. HERO COM PREVIEW REAL DO PRODUTO */}
        <section className="relative pt-16 sm:pt-24 pb-20 sm:pb-28">
          <div aria-hidden="true" className="hero-grid pointer-events-none absolute inset-0 opacity-60 dark:opacity-50" />

          <div className="relative max-w-5xl mx-auto px-5 sm:px-8 space-y-14">
            <Reveal className="max-w-3xl mx-auto text-center space-y-7">
              <div className="flex justify-center">
                <EviDocsBrand sizeClass="text-5xl sm:text-6xl" />
              </div>

              <h1 className="text-3xl sm:text-5xl lg:text-[52px] font-extrabold tracking-tight leading-[1.1] text-[#2d0a33] dark:text-white">
                Auditoria da documentação trabalhista de terceirizadas, do PDF escaneado à nota de conformidade.
              </h1>

              <div className="flex flex-wrap items-center justify-center gap-3.5 pt-2">
                <a
                  href={DEMO_URL}
                  className="inline-flex items-center gap-2 px-6 py-3.5 rounded-xl text-sm font-semibold bg-gradient-to-r from-[#9333ea] to-[#7e22ce] hover:brightness-110 text-white shadow-lg shadow-[#9333ea]/30 transition-all"
                >
                  Acessar demo do sistema
                  <ArrowRight className="w-4 h-4" />
                </a>
                <a
                  href="/na-tela"
                  onClick={(e) => navegarPara('/na-tela', e)}
                  className="inline-flex items-center gap-2 px-5 py-3.5 rounded-xl text-sm font-semibold border border-[#e2d8ea] dark:border-[#2e1e38] bg-white/75 dark:bg-[#1a1020]/75 text-[#4c3e57] dark:text-[#d3c7dc] hover:border-[#bd79ff]/60 hover:text-[#2d0a33] dark:hover:text-white transition-all"
                >
                  Ver o produto na tela
                  <ArrowDown className="w-4 h-4" />
                </a>
              </div>
            </Reveal>

            {/* Preview real em destaque logo no Hero */}
            <Reveal delayMs={120}>
              <div className="relative mx-auto max-w-4xl">
                <div
                  aria-hidden="true"
                  className="absolute -inset-2 rounded-3xl bg-gradient-to-r from-[#ff79e7]/25 via-[#bd79ff]/20 to-[#5ddfff]/25 blur-2xl opacity-70 dark:opacity-80"
                />
                <div className="relative rounded-2xl p-[1px] bg-gradient-to-b from-[#ff79e7]/45 via-[#bd79ff]/30 to-[#5ddfff]/40 shadow-2xl shadow-black/25">
                  <div className="rounded-[15px] overflow-hidden bg-[#140c17]">
                    <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 bg-[#120a15]">
                      <div className="flex items-center gap-1.5" aria-hidden="true">
                        <span className="w-2.5 h-2.5 rounded-full bg-[#ff79e7]/75" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#bd79ff]/75" />
                        <span className="w-2.5 h-2.5 rounded-full bg-[#5ddfff]/75" />
                      </div>
                      <span className="text-[11px] font-mono text-[#a89ab3]">evidocs / documentos</span>
                      <span className="text-[11px] font-medium text-[#5ddfff]">Tela real</span>
                    </div>
                    <img
                      src="/screens/hero-sistema.png"
                      alt="Tela inicial real do EviDocs mostrando 6 documentos classificados automaticamente pela IA com 100% de precisão e 0 aguardando revisão"
                      className="w-full block"
                    />
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* 2. O PROBLEMA */}
        <section id="problema" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 space-y-12">
            <Reveal className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                O problema
              </div>
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
                Quem contrata terceirizada responde junto pelos direitos dos funcionários dela.
              </h2>
            </Reveal>

            <div className="grid md:grid-cols-3 gap-6">
              {DORES.map((dor, idx) => {
                const Icone = dor.icone
                return (
                  <Reveal key={dor.titulo} delayMs={idx * 90}>
                    <div className="group h-full rounded-2xl border border-[#ece8ef] dark:border-[#281933] bg-white/85 dark:bg-[#190f1f]/85 p-7 space-y-4 hover:-translate-y-1 hover:border-[#bd79ff]/50 transition-all duration-300 shadow-sm hover:shadow-xl hover:shadow-[#9333ea]/5">
                      <div className="flex items-center justify-between">
                        <div className="p-2.5 rounded-xl bg-[#f4e8f7] dark:bg-[#2b1535] text-[#7e22ce] dark:text-[#f38df9]">
                          <Icone className="w-5 h-5" />
                        </div>
                        <span className="text-xs font-mono font-bold text-[#a394b0] dark:text-[#5c4b69]">
                          {dor.num}
                        </span>
                      </div>
                      <h3 className="text-lg font-bold text-[#2d0a33] dark:text-white">{dor.titulo}</h3>
                      <p className="text-sm text-[#5b4d66] dark:text-[#b7a8c2] leading-relaxed">{dor.texto}</p>
                    </div>
                  </Reveal>
                )
              })}
            </div>
          </div>
        </section>

        {/* 3. A SOLUÇÃO — PIPELINE COM FEIXE ANIMADO */}
        <section id="solucao" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 space-y-12">
            <Reveal className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                A solução
              </div>
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
                Um lote entra inteiro. A auditoria sai pronta.
              </h2>
            </Reveal>

            <Reveal>
              <div className="relative">
                {/* Linha conectora animada no desktop */}
                <div
                  aria-hidden="true"
                  className="hidden sm:block absolute left-8 right-8 top-9 h-[2px] bg-[#e6dfec] dark:bg-[#2a1c34] z-0"
                >
                  <div
                    className="h-full bg-gradient-to-r from-[#ff79e7] via-[#bd79ff] to-[#5ddfff] transition-all duration-500 ease-out"
                    style={{ width: `${((etapaAtiva - 1) / 4) * 100}%` }}
                  />
                </div>

                <div className="relative z-10 grid sm:grid-cols-5 gap-4">
                  {ETAPAS_PIPELINE.map((passo) => {
                    const destacada = etapaAtiva === passo.num
                    const concluida = passo.num < etapaAtiva
                    const Icone = passo.icone
                    return (
                      <button
                        key={passo.num}
                        type="button"
                        onClick={() => setEtapaAtiva(passo.num)}
                        className={`text-left rounded-2xl border p-5 transition-all duration-400 cursor-pointer ${
                          destacada
                            ? 'border-[#bd79ff] bg-white dark:bg-[#261431] -translate-y-1.5 shadow-xl shadow-[#9333ea]/15'
                            : 'border-[#ece8ef] dark:border-[#27192f] bg-white/80 dark:bg-[#180f1e]/90 hover:border-[#bd79ff]/50'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <div
                            className={`w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-300 ${
                              destacada
                                ? 'bg-gradient-to-br from-[#ff79e7] to-[#7c8cff] text-[#140c17] shadow-md shadow-[#bd79ff]/30'
                                : concluida
                                  ? 'bg-[#f4e8f7] dark:bg-[#2e173a] text-[#7e22ce] dark:text-[#f38df9]'
                                  : 'bg-[#f3edf6] dark:bg-[#22152b] text-[#7a6d85] dark:text-[#8c7c99]'
                            }`}
                          >
                            <Icone className="w-4 h-4" />
                          </div>
                          <span
                            className={`text-xs font-mono font-bold ${
                              destacada ? 'text-[#7e22ce] dark:text-[#5ddfff]' : 'text-[#a394b0] dark:text-[#5e4d6c]'
                            }`}
                          >
                            0{passo.num}
                          </span>
                        </div>
                        <div className="mt-4 text-sm sm:text-base font-bold text-[#2d0a33] dark:text-white">
                          {passo.titulo}
                        </div>
                        <p className="mt-1.5 text-xs text-[#5b4d66] dark:text-[#b2a4bc] leading-relaxed">
                          {passo.detalhe}
                        </p>
                      </button>
                    )
                  })}
                </div>
              </div>
            </Reveal>

            <Reveal delayMs={120}>
              <div className="rounded-2xl border border-[#bd79ff]/30 bg-[#f4e8f7]/50 dark:bg-[#22122b]/70 px-5 py-4 flex items-center gap-3.5 text-sm sm:text-base text-[#3d2d47] dark:text-[#e9dff0]">
                <UserCheck className="w-5 h-5 shrink-0 text-[#7e22ce] dark:text-[#f38df9]" />
                <span>
                  <strong className="text-[#2d0a33] dark:text-white">Na dúvida, um humano revisa:</strong> documento de
                  baixa confiança vai para a fila de revisão.
                </span>
              </div>
            </Reveal>
          </div>
        </section>

        {/* 4. NA TELA (CAPTURAS REAIS) */}
        <section id="na-tela" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8">
            <Reveal>
              <ScreenShowcase />
            </Reveal>
          </div>
        </section>

        {/* 5. RESULTADOS — NÚMEROS MONUMENTAIS */}
        <section id="resultados" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 space-y-12">
            <Reveal className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                Resultados
              </div>
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
                Testamos com documentos que o sistema nunca tinha visto.
              </h2>
            </Reveal>

            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
              {[
                {
                  accent: 'from-[#ff79e7] to-[#bd79ff]',
                  valor: (
                    <>
                      <CountUp target={93} />
                      <span className="text-2xl font-bold opacity-70"> de 93</span>
                    </>
                  ),
                  texto: 'documentos separados certinho, mesmo com todos da mesma empresa',
                },
                {
                  accent: 'from-[#bd79ff] to-[#7c8cff]',
                  valor: (
                    <>
                      <CountUp target={81} />
                      <span className="text-2xl font-bold opacity-70"> de 82</span>
                    </>
                  ),
                  texto: 'documentos separados certinho, com empresas misturadas',
                },
                {
                  accent: 'from-[#7c8cff] to-[#5ddfff]',
                  valor: <CountUp target={100} suffix="%" />,
                  texto: 'dos documentos classificados no tipo certo',
                },
                {
                  accent: 'from-[#ff79e7] via-[#bd79ff] to-[#5ddfff]',
                  valor: <CountUp target={0.004} decimals={3} prefix="US$ " />,
                  texto: 'de IA por documento: menos de 1 centavo de dólar',
                },
              ].map((card, idx) => (
                <Reveal key={card.texto} delayMs={idx * 80}>
                  <div className="relative h-full rounded-2xl border border-[#e6dfec] dark:border-[#2c1c36] bg-white dark:bg-[#190f1f] overflow-hidden p-7 space-y-4 hover:-translate-y-1 transition-transform duration-300 shadow-sm hover:shadow-xl hover:shadow-[#9333ea]/10">
                    <div className={`absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r ${card.accent}`} />
                    <div
                      className={`text-4xl sm:text-5xl font-extrabold tracking-tight tabular-nums bg-gradient-to-r ${card.accent} bg-clip-text text-transparent`}
                    >
                      {card.valor}
                    </div>
                    <p className="text-sm text-[#5b4d66] dark:text-[#b7a8c2] leading-relaxed">{card.texto}</p>
                  </div>
                </Reveal>
              ))}
            </div>

            <Reveal delayMs={150}>
              <p className="text-xs sm:text-sm text-[#7a6d85] dark:text-[#9c8ea6]">
                Testes com documentos simulados. Próximo passo: validar com documentos reais.
              </p>
            </Reveal>
          </div>
        </section>

        {/* 6. MODELO DE NEGÓCIO */}
        <section id="negocio" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 space-y-10">
            <Reveal className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                Modelo de negócio
              </div>
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
                Cobramos por documento processado.
              </h2>
            </Reveal>

            <div className="grid lg:grid-cols-5 gap-6 items-stretch">
              <Reveal className="lg:col-span-3">
                <div className="h-full rounded-2xl border border-[#e6dfec] dark:border-[#2c1c36] bg-white dark:bg-[#190f1f] overflow-hidden shadow-sm">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="border-b border-[#ece8ef] dark:border-[#27192f] bg-[#f8f4fa] dark:bg-[#140c17] text-xs uppercase tracking-wider text-[#7a6d85] dark:text-[#9c8ea6]">
                        <th className="py-4 px-5 font-semibold">Custo de IA medido</th>
                        <th className="py-4 px-4 font-semibold text-right text-[#7e22ce] dark:text-[#f38df9]">
                          Até dez/2026
                        </th>
                        <th className="py-4 px-5 font-semibold text-right">A partir de 2027</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#ece8ef] dark:divide-[#27192f] text-sm">
                      {CUSTOS.map((row) => (
                        <tr key={row.item} className="hover:bg-[#faf6fc] dark:hover:bg-[#211329]/50 transition-colors">
                          <td className="py-4 px-5 font-medium text-[#2d0a33] dark:text-[#e9dff0]">{row.item}</td>
                          <td className="py-4 px-4 text-right font-mono font-bold text-[#7e22ce] dark:text-[#f38df9]">
                            {row.ate2026}
                          </td>
                          <td className="py-4 px-5 text-right font-mono text-[#5b4d66] dark:text-[#b7a8c2]">
                            {row.de2027}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Reveal>

              <Reveal delayMs={100} className="lg:col-span-2">
                <div className="h-full rounded-2xl p-[1px] bg-gradient-to-br from-[#ff79e7]/50 via-[#bd79ff]/40 to-[#5ddfff]/50">
                  <div className="h-full rounded-[15px] bg-gradient-to-br from-[#faf3fc] to-white dark:from-[#261432] dark:to-[#180e1f] p-7 flex flex-col justify-between space-y-5">
                    <div className="space-y-2.5">
                      <span className="inline-block text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                        Preço · No piloto
                      </span>
                      <p className="text-xl font-extrabold text-[#2d0a33] dark:text-white leading-snug">
                        Definido pelo tempo de análise que o cliente economiza.
                      </p>
                    </div>
                    <p className="text-sm text-[#4c3e57] dark:text-[#d3c7dc] leading-relaxed">
                      Com IA abaixo de 1 centavo de dólar por documento, sobra margem.
                    </p>
                  </div>
                </div>
              </Reveal>
            </div>

            <Reveal delayMs={140}>
              <p className="text-xs text-[#7a6d85] dark:text-[#9c8ea6]">
                Custo calculado com os tokens reais de 1.424 respostas dos modelos e o preço público do Gemini 3.8 Flash,
                que dobra em 2027. Infraestrutura não incluída.
              </p>
            </Reveal>
          </div>
        </section>

        {/* 7. POR QUE CONFIAR */}
        <section id="confianca" className="py-20 sm:py-28 border-t border-[#ece8ef] dark:border-[#27192f]/70">
          <div className="max-w-5xl mx-auto px-5 sm:px-8 space-y-12">
            <Reveal className="max-w-3xl space-y-3">
              <div className="text-xs font-semibold uppercase tracking-[0.16em] text-[#7e22ce] dark:text-[#f38df9]">
                Por que confiar
              </div>
              <h2 className="text-3xl sm:text-4xl font-extrabold tracking-tight leading-tight text-[#2d0a33] dark:text-white">
                A IA só lê. Quem decide é código.
              </h2>
            </Reveal>

            <div className="grid md:grid-cols-3 gap-6">
              {PILARES_CONFIANCA.map((pilar, idx) => {
                const Icone = pilar.icone
                return (
                  <Reveal key={pilar.num} delayMs={idx * 90}>
                    <div className="relative h-full rounded-2xl border border-[#ece8ef] dark:border-[#281933] bg-white/85 dark:bg-[#190f1f]/85 p-7 space-y-5 overflow-hidden hover:-translate-y-1 hover:border-[#bd79ff]/50 transition-all duration-300">
                      <span
                        aria-hidden="true"
                        className="pointer-events-none absolute -right-2 -top-4 text-7xl font-extrabold font-mono text-[#9333ea]/[0.06] dark:text-white/[0.04] select-none"
                      >
                        {pilar.num}
                      </span>
                      <div className="inline-flex items-center gap-2.5">
                        <div className="p-2.5 rounded-xl bg-[#f4e8f7] dark:bg-[#2b1535] text-[#7e22ce] dark:text-[#5ddfff]">
                          <Icone className="w-5 h-5" />
                        </div>
                        <span className="text-sm font-mono font-bold bg-gradient-to-r from-[#ff79e7] to-[#5ddfff] bg-clip-text text-transparent">
                          {pilar.num}
                        </span>
                      </div>
                      <p className="relative text-base font-semibold text-[#2d0a33] dark:text-[#f0e8f5] leading-relaxed">
                        {pilar.texto}
                      </p>
                    </div>
                  </Reveal>
                )
              })}
            </div>

            <Reveal delayMs={160}>
              <div className="rounded-2xl p-[1px] bg-gradient-to-r from-[#ff79e7]/45 via-[#bd79ff]/35 to-[#5ddfff]/45">
                <div className="rounded-[15px] bg-white dark:bg-[#190f1f] px-6 sm:px-8 py-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <p className="text-lg sm:text-xl font-extrabold tracking-tight text-[#2d0a33] dark:text-white">
                    Próximo passo: um lote real de cliente para validar.
                  </p>
                  <a
                    href="/na-tela"
                    onClick={(e) => navegarPara('/na-tela', e)}
                    className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-semibold bg-[#f4e8f7] dark:bg-[#2c1638] text-[#5c1363] dark:text-[#f38df9] hover:brightness-110 transition-all shrink-0"
                  >
                    Rever as telas
                    <ArrowRight className="w-4 h-4" />
                  </a>
                </div>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      {/* Footer limpo */}
      <footer className="border-t border-[#ece8ef] dark:border-[#27192f] py-8">
        <div className="max-w-5xl mx-auto px-5 sm:px-8 flex items-center justify-between gap-4">
          <EviDocsBrand sizeClass="text-xl" />
          <a
            href="/"
            onClick={(e) => navegarPara('/', e)}
            className="inline-flex items-center gap-1.5 text-xs font-medium text-[#6e6378] dark:text-[#a89ab3] hover:text-[#2d0a33] dark:hover:text-white transition-colors"
          >
            Voltar ao topo
            <ArrowUp className="w-3.5 h-3.5" />
          </a>
        </div>
      </footer>
    </div>
  )
}

export default App
