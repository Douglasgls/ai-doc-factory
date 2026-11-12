import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  FileText,
  Info,
  X,
} from 'lucide-react'
import { apiService } from '../services/api'
import { formatarData } from './auditoriaPonto'
import {
  ORDEM_CRITERIOS,
  corDaFaixa,
  formatarPercentual,
  formatarPontos,
  gerarResumo,
  listaPt,
  motivosProvisorio,
  regraDaPendencia,
  rotuloCampo,
  rotuloEmFrase,
  rotuloTipoDoc,
  somaDescontos,
  type CriterioChave,
  type ConformidadeEmpresa,
  type CorFaixa,
  type Rotulos,
} from './conformidadeEmpresa'

interface Props {
  cnpj: string
  razaoSocial: string
  onClose: () => void
}

const ROTULO_CRITERIO_CARD: Record<CriterioChave, string> = {
  completude: 'Documentos enviados',
  validade: 'Documentos válidos',
  consistencia: 'Dados consistentes',
}

const CONTAGEM_CURTA: Record<CriterioChave, (bons: number, total: number) => string> = {
  completude: (b, t) => `${b} de ${t} ${t === 1 ? 'obrigatório enviado' : 'obrigatórios enviados'}`,
  validade: (b, t) => `${b} de ${t} ${t === 1 ? 'documento válido' : 'documentos válidos'}`,
  consistencia: (b, t) => `${b} de ${t} ${t === 1 ? 'dado consistente' : 'dados consistentes'}`,
}

function capitalizarFrase(texto: string): string {
  if (!texto) return ''
  return texto.charAt(0).toUpperCase() + texto.slice(1)
}

export function formatarCnpjVisual(valor: string): string {
  const digitos = valor.replace(/\D/g, '')
  if (digitos.length !== 14) return valor
  return `${digitos.slice(0, 2)}.${digitos.slice(2, 5)}.${digitos.slice(5, 8)}/${digitos.slice(8, 12)}-${digitos.slice(12, 14)}`
}

interface CardAcao {
  chave: string
  icone: 'arquivo' | 'relogio' | 'alerta'
  cor: 'vermelho' | 'ambar'
  titulo: string
  descricao: string
  badge: string
}

const AnelNota: React.FC<{ score: number | null; faixa: CorFaixa }> = ({ score, faixa }) => {
  const raio = 40
  const circunferencia = 2 * Math.PI * raio
  const percentual = score != null ? Math.max(0, Math.min(100, score)) : 0
  // Quando a nota é 0, exibe o anel completo na cor de alerta com o marcador no topo (fiel ao Figma)
  const offset =
    score === 0
      ? 0
      : score != null
        ? circunferencia - (percentual / 100) * circunferencia
        : circunferencia

  const corTrajeto =
    faixa === 'verde'
      ? '#10b981'
      : faixa === 'ambar'
        ? '#f59e0b'
        : '#ef4444'

  const corFundoTrilha =
    faixa === 'verde'
      ? 'stroke-emerald-100 dark:stroke-emerald-950/60'
      : faixa === 'ambar'
        ? 'stroke-amber-100 dark:stroke-amber-950/60'
        : 'stroke-red-100 dark:stroke-red-950/60'

  return (
    <div
      className="relative w-24 h-24 sm:w-[100px] sm:h-[100px] shrink-0 flex items-center justify-center"
      role="img"
      aria-label={score != null ? `Nota ${score} de 100` : 'Ainda sem nota'}
    >
      <svg className="w-full h-full -rotate-90" viewBox="0 0 100 100" aria-hidden="true">
        <circle
          cx="50"
          cy="50"
          r={raio}
          fill="none"
          strokeWidth="6.5"
          className={corFundoTrilha}
        />
        {score != null && (
          <circle
            cx="50"
            cy="50"
            r={raio}
            fill="none"
            stroke={corTrajeto}
            strokeWidth="6.5"
            strokeLinecap="round"
            strokeDasharray={circunferencia}
            strokeDashoffset={offset}
            className="transition-all duration-500"
          />
        )}
        {score != null && (
          <circle
            cx="90"
            cy="50"
            r="3.2"
            fill="#ffffff"
            stroke={corTrajeto}
            strokeWidth="2"
          />
        )}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
        <span className="text-3xl font-extrabold leading-none text-[#1e1324] dark:text-white">
          {score != null ? score : '—'}
        </span>
        <span className="text-xs font-medium text-[#7c7085] dark:text-[#b4a7c0] mt-1">/100</span>
      </div>
    </div>
  )
}

const ConformidadeEmpresaModal: React.FC<Props> = ({ cnpj, razaoSocial, onClose }) => {
  const [dados, setDados] = useState<ConformidadeEmpresa | null>(null)
  const [erro, setErro] = useState<string | null>(null)
  const [rotulos, setRotulos] = useState<Rotulos>({})
  const [recarga, setRecarga] = useState(0)
  const [detalhesAbertos, setDetalhesAbertos] = useState(false)
  const acordeaoRef = useRef<HTMLDivElement>(null)

  const carregar = useCallback(() => {
    setDados(null)
    setErro(null)
    setRecarga((n) => n + 1)
  }, [])

  useEffect(() => {
    let ativo = true
    apiService
      .getEmpresaConformidade(cnpj)
      .then((r) => {
        if (ativo) setDados(r as unknown as ConformidadeEmpresa)
      })
      .catch((e: unknown) => {
        if (ativo) setErro(e instanceof Error ? e.message : 'Não foi possível carregar a conformidade.')
      })
    return () => {
      ativo = false
    }
  }, [cnpj, recarga])

  useEffect(() => {
    let ativo = true
    apiService
      .getTipos()
      .then((ts) => {
        if (ativo) setRotulos(Object.fromEntries(ts.map((t) => [t.slug, t.nome])))
      })
      .catch(() => undefined)
    return () => {
      ativo = false
    }
  }, [])

  useEffect(() => {
    const aoTeclar = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', aoTeclar)
    return () => window.removeEventListener('keydown', aoTeclar)
  }, [onClose])

  // Auto-scroll suave quando o usuário expande "Entenda como chegamos a esta nota"
  useEffect(() => {
    if (!detalhesAbertos) return
    const timer = setTimeout(() => {
      acordeaoRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
    }, 80)
    return () => clearTimeout(timer)
  }, [detalhesAbertos])

  const g = dados?.geral
  const faixa: CorFaixa = g?.score != null ? corDaFaixa(g.classificacao) : 'ambar'
  const motivos = useMemo(() => (g ? motivosProvisorio(g, rotulos) : []), [g, rotulos])
  const totalDescontado = g ? somaDescontos(g) : 0

  const ausentes = useMemo(
    () => (g ? g.descontos.filter((d) => d.regra === 'obrigatorio_ausente') : []),
    [g]
  )
  const vencidos = useMemo(
    () => (g ? g.descontos.filter((d) => d.regra === 'documento_vencido') : []),
    [g]
  )
  const divergentes = useMemo(
    () => (g ? g.descontos.filter((d) => d.regra === 'campo_divergente') : []),
    [g]
  )

  // Tipos confirmados que estão em análise / revisão manual
  const tiposEmRevisaoConfirmada = useMemo(() => {
    if (!g) return []
    const slugs = new Set<string>()
    for (const p of g.pendencias) {
      if (regraDaPendencia(p) === 'pendente_revisao' && p.tipo) {
        slugs.add(p.tipo)
      }
    }
    return [...slugs]
  }, [g])

  // Tipos obrigatórios que ainda podem ser cobertos por documento pendente de identificação
  const tiposPendenteObrigatorio = useMemo(() => {
    if (!g) return []
    const slugs = new Set<string>()
    for (const p of g.pendencias) {
      if (regraDaPendencia(p) === 'pendente_obrigatorio' && p.tipo) {
        slugs.add(p.tipo)
      }
    }
    return [...slugs]
  }, [g])

  const qtdPendenciasRevisao = useMemo(() => {
    if (!g) return 0
    return g.pendencias.filter((p) => regraDaPendencia(p) === 'pendente_revisao').length
  }, [g])

  // Título e subtítulo principais do card de nota (100% baseados nos dados reais)
  const { tituloHero, subtituloHero, etiquetaHero } = useMemo(() => {
    if (!dados || !g) {
      return { tituloHero: '', subtituloHero: '', etiquetaHero: '' }
    }
    const etiqueta =
      g.classificacao === 'Regular'
        ? 'DOCUMENTAÇÃO REGULAR'
        : g.classificacao === 'Atenção'
          ? 'ATENÇÃO NECESSÁRIA'
          : 'AÇÃO NECESSÁRIA'

    const sufixoEmAnalise =
      qtdPendenciasRevisao > 0
        ? ` ${
            qtdPendenciasRevisao === 1
              ? 'Um documento já está sendo analisado.'
              : `${qtdPendenciasRevisao} documentos já estão sendo analisados.`
          }`
        : ''

    if (ausentes.length > 0) {
      return {
        etiquetaHero: etiqueta,
        tituloHero:
          ausentes.length === 1
            ? 'Falta 1 documento obrigatório'
            : `Faltam ${ausentes.length} documentos obrigatórios`,
        subtituloHero: `Envie os documentos abaixo para melhorar a nota.${sufixoEmAnalise}`,
      }
    }

    if (vencidos.length > 0) {
      return {
        etiquetaHero: etiqueta,
        tituloHero:
          vencidos.length === 1
            ? '1 documento obrigatório está vencido'
            : `${vencidos.length} documentos obrigatórios estão vencidos`,
        subtituloHero: `Solicite a renovação dos documentos vencidos e envie um novo lote.${sufixoEmAnalise}`,
      }
    }

    if (divergentes.length > 0) {
      return {
        etiquetaHero: etiqueta,
        tituloHero:
          divergentes.length === 1
            ? '1 divergência cadastral encontrada'
            : `${divergentes.length} divergências cadastrais encontradas`,
        subtituloHero: `Confira os dados divergentes entre os documentos enviados.${sufixoEmAnalise}`,
      }
    }

    if (g.score == null) {
      return {
        etiquetaHero: 'EM ANÁLISE',
        tituloHero: 'Aguardando conclusão da análise',
        subtituloHero:
          'Os documentos enviados ainda estão em análise ou revisão manual. A nota será calculada automaticamente.',
      }
    }

    if (g.descontos.length === 0) {
      return {
        etiquetaHero: etiqueta,
        tituloHero: 'Documentação obrigatória em dia',
        subtituloHero: `Todos os critérios avaliados foram atendidos sem descontos na nota.${sufixoEmAnalise}`,
      }
    }

    return {
      etiquetaHero: etiqueta,
      tituloHero: `${g.descontos.length} ${g.descontos.length === 1 ? 'ponto exige atenção' : 'pontos exigem atenção'}`,
      subtituloHero: gerarResumo(dados, rotulos),
    }
  }, [ausentes.length, dados, divergentes.length, g, qtdPendenciasRevisao, rotulos, vencidos.length])

  // Texto natural para o banner amarelo ("Este resultado ainda pode mudar")
  const textoBannerProvisorio = useMemo(() => {
    if (!g || !g.provisorio) return ''
    if (tiposEmRevisaoConfirmada.length === 1) {
      const nomeCurto = rotuloEmFrase(tiposEmRevisaoConfirmada[0], rotulos)
      return `O ${nomeCurto} está em revisão manual. Quando a conferência terminar, a nota será atualizada automaticamente.`
    }
    if (tiposEmRevisaoConfirmada.length > 1) {
      const nomes = listaPt(tiposEmRevisaoConfirmada.map((t) => rotuloEmFrase(t, rotulos)))
      return `Os documentos (${nomes}) estão em revisão manual. Quando a conferência terminar, a nota será atualizada automaticamente.`
    }
    if (tiposPendenteObrigatorio.length > 0) {
      const nomes = listaPt(tiposPendenteObrigatorio.map((t) => rotuloEmFrase(t, rotulos)))
      return `Há documentos em processamento que podem corresponder a ${nomes}. A nota será recalculada após a identificação.`
    }
    return (
      motivos[0] ||
      'Há documentos em análise ou revisão. Quando o processamento terminar, a nota será atualizada automaticamente.'
    )
  }, [g, motivos, rotulos, tiposEmRevisaoConfirmada, tiposPendenteObrigatorio])

  // Cards da seção "1. O que você precisa fazer"
  const cardsAcao = useMemo<CardAcao[]>(() => {
    if (!g) return []
    const lista: CardAcao[] = []

    if (ausentes.length > 0) {
      const nomes = listaPt(ausentes.map((d) => rotuloEmFrase(d.tipo, rotulos)))
      lista.push({
        chave: 'ausentes',
        icone: 'arquivo',
        cor: 'vermelho',
        titulo: 'Solicite os documentos que faltam',
        descricao: `${capitalizarFrase(nomes)}.`,
        badge: `${ausentes.length} ${ausentes.length === 1 ? 'documento' : 'documentos'}`,
      })
    }

    if (qtdPendenciasRevisao > 0 || tiposEmRevisaoConfirmada.length > 0) {
      const nomeUnico =
        tiposEmRevisaoConfirmada.length === 1 ? rotuloEmFrase(tiposEmRevisaoConfirmada[0], rotulos) : null
      lista.push({
        chave: 'em_analise',
        icone: 'relogio',
        cor: 'ambar',
        titulo: nomeUnico
          ? `Acompanhe a revisão do ${nomeUnico}`
          : 'Acompanhe os documentos em revisão manual',
        descricao: 'Não é preciso fazer nada agora. Avisaremos quando a revisão terminar.',
        badge: 'Em revisão',
      })
    }

    if (tiposPendenteObrigatorio.length > 0 && tiposEmRevisaoConfirmada.length === 0) {
      const nomes = listaPt(tiposPendenteObrigatorio.map((t) => rotuloEmFrase(t, rotulos)))
      lista.push({
        chave: 'aguardando_identificacao',
        icone: 'relogio',
        cor: 'ambar',
        titulo: 'Aguarde a identificação de novos documentos',
        descricao: `Documentos enviados podem cobrir ${nomes}. A conformidade será atualizada após o reconhecimento.`,
        badge: 'Processando',
      })
    }

    if (vencidos.length > 0) {
      const detalhes = vencidos.map((d) => {
        const nome = rotuloEmFrase(d.tipo, rotulos)
        const m = /venceu em (\d{4}-\d{2}-\d{2})/.exec(d.detalhe)
        return m ? `${nome} (venceu em ${formatarData(m[1])})` : nome
      })
      lista.push({
        chave: 'vencidos',
        icone: 'alerta',
        cor: 'vermelho',
        titulo: 'Solicite a renovação dos vencidos',
        descricao: `${capitalizarFrase(listaPt(detalhes))}.`,
        badge: `${vencidos.length} ${vencidos.length === 1 ? 'vencido' : 'vencidos'}`,
      })
    }

    if (divergentes.length > 0) {
      const campos = [...new Set(divergentes.map((d) => rotuloCampo(d.campo)))]
      lista.push({
        chave: 'divergentes',
        icone: 'alerta',
        cor: 'ambar',
        titulo: 'Confira os dados divergentes',
        descricao: `Divergência em ${listaPt(campos)} entre documentos enviados.`,
        badge: `${divergentes.length} ${divergentes.length === 1 ? 'divergência' : 'divergências'}`,
      })
    }

    return lista
  }, [ausentes, divergentes, g, qtdPendenciasRevisao, rotulos, tiposEmRevisaoConfirmada, tiposPendenteObrigatorio, vencidos])

  // Fórmula e explicação do "Cálculo atual"
  const { textoCalculo, formulaCalculo } = useMemo(() => {
    if (!g) return { textoCalculo: '', formulaCalculo: '' }
    if (g.score == null) {
      return {
        textoCalculo:
          'O cálculo da nota ainda não está disponível porque há documentos em análise ou revisão manual.',
        formulaCalculo: 'Aguardando análise',
      }
    }
    const scoreFinal = g.score
    if (g.descontos.length === 0) {
      return {
        textoCalculo: 'A nota parte de 100 e não possui nenhum desconto aplicado.',
        formulaCalculo: `100 - 0 = ${scoreFinal}`,
      }
    }

    const primeiroPonto = g.descontos[0].pontos
    const todosIguais = g.descontos.every((d) => Math.abs(d.pontos - primeiroPonto) < 0.01)
    const soAusentes = g.descontos.every((d) => d.regra === 'obrigatorio_ausente')

    if (todosIguais && soAusentes) {
      return {
        textoCalculo: `A nota parte de 100 e perde ${formatarPontos(primeiroPonto)} pontos por documento obrigatório ausente.`,
        formulaCalculo: `100 - (${g.descontos.length} × ${formatarPontos(primeiroPonto)}) = ${scoreFinal}`,
      }
    }

    return {
      textoCalculo: `A nota parte de 100 e desconta ${formatarPontos(totalDescontado)} pontos pelas pendências encontradas.`,
      formulaCalculo: `100 - ${formatarPontos(totalDescontado)} = ${scoreFinal}`,
    }
  }, [g, totalDescontado])

  // Lista de "Documentos considerados" ordenada (Em análise / Enviados primeiro, depois Não enviados)
  const documentosConsiderados = useMemo(() => {
    if (!dados || !g) return []
    const entradas = Object.entries(dados.por_tipo).filter(([tipo, aval]) => {
      const qtd = dados.documentos_por_tipo[tipo] ?? 0
      return aval.criterios.completude.aplicavel || qtd > 0
    })

    const mapearStatus = (
      tipo: string,
      aval: (typeof entradas)[number][1]
    ): {
      ordem: number
      statusLabel: string
      statusTipo: 'analise' | 'enviado' | 'ausente' | 'problema'
    } => {
      const comp = aval.criterios.completude
      const qtd = dados.documentos_por_tipo[tipo] ?? 0
      const temVencido = g.descontos.some((d) => d.tipo === tipo && d.regra === 'documento_vencido')
      const temDivergencia = g.descontos.some(
        (d) => d.tipo === tipo && d.regra === 'campo_divergente'
      )
      const emRevisaoConfirmada = tiposEmRevisaoConfirmada.includes(tipo)
      const podeSerIdentificado = tiposPendenteObrigatorio.includes(tipo) || comp.pendente

      if (emRevisaoConfirmada) {
        return { ordem: 1, statusLabel: 'Em revisão', statusTipo: 'analise' }
      }
      if (podeSerIdentificado && qtd === 0) {
        return { ordem: 1, statusLabel: 'Aguardando identificação', statusTipo: 'analise' }
      }
      if (temVencido) {
        return { ordem: 2, statusLabel: 'Vencido', statusTipo: 'problema' }
      }
      if (temDivergencia) {
        return { ordem: 2, statusLabel: 'Com divergência', statusTipo: 'problema' }
      }
      if (comp.nota === 1 || qtd > 0) {
        return { ordem: 2, statusLabel: 'Enviado', statusTipo: 'enviado' }
      }
      return { ordem: 3, statusLabel: 'Não enviado', statusTipo: 'ausente' }
    }

    return entradas
      .map(([tipo, aval]) => ({
        tipo,
        nome: rotuloTipoDoc(tipo, rotulos),
        ...mapearStatus(tipo, aval),
      }))
      .sort((a, b) => a.ordem - b.ordem)
  }, [dados, g, rotulos, tiposEmRevisaoConfirmada, tiposPendenteObrigatorio])

  const cnpjFormatado = formatarCnpjVisual(cnpj)
  const subtituloEmpresa =
    razaoSocial && razaoSocial !== cnpj && !razaoSocial.startsWith('Empresa ')
      ? `${razaoSocial} · CNPJ ${cnpjFormatado}`
      : `Empresa · CNPJ ${cnpjFormatado}`

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-5 bg-black/65 backdrop-blur-sm animate-in fade-in duration-200"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-conformidade-titulo"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-[720px] bg-white dark:bg-[#160f1c] rounded-3xl border border-[#e9e3ee] dark:border-[#2e1f38] shadow-2xl overflow-hidden max-h-[92vh] flex flex-col"
      >
        {/* Cabeçalho */}
        <div className="px-6 sm:px-8 pt-6 pb-5 border-b border-[#efebf3] dark:border-[#25192e] flex items-start justify-between gap-4">
          <div className="min-w-0">
            <span className="text-[11px] font-bold tracking-[0.08em] uppercase text-[#7e22ce] dark:text-[#d8b4fe]">
              AVALIAÇÃO DOCUMENTAL
            </span>
            <h3
              id="modal-conformidade-titulo"
              className="text-xl sm:text-2xl font-extrabold text-[#1e1324] dark:text-white mt-0.5 tracking-tight"
            >
              Resultado da análise
            </h3>
            <p className="text-xs sm:text-[13px] text-[#6e6378] dark:text-[#b4a7c0] mt-1 truncate">
              {subtituloEmpresa}
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar janela de resultado da análise"
            onClick={onClose}
            className="p-2 rounded-xl text-[#6e6378] dark:text-[#b4a7c0] hover:text-[#1e1324] dark:hover:text-white hover:bg-[#f4eff7] dark:hover:bg-[#26192e] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9333ea] transition-colors cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Corpo com scroll */}
        <div className="px-6 sm:px-8 py-6 overflow-y-auto space-y-6">
          {!dados && !erro && (
            <div className="flex items-center justify-center gap-3 py-14 text-sm text-[#6e6378] dark:text-[#b4a7c0]">
              <Clock className="w-5 h-5 text-[#9333ea] animate-spin" />
              <span>Carregando resultado da análise...</span>
            </div>
          )}

          {erro && (
            <div className="p-5 rounded-2xl border border-red-200 dark:border-red-900/40 bg-red-50 dark:bg-red-950/20 text-sm text-red-700 dark:text-red-300 space-y-3">
              <p>{erro}</p>
              <button
                type="button"
                onClick={carregar}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-red-600 hover:bg-red-700 text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-500 cursor-pointer"
              >
                Tentar de novo
              </button>
            </div>
          )}

          {dados && g && (
            <>
              {/* 1. Card Principal: Anel da Nota + Chamada Principal */}
              <div
                className={`p-5 sm:p-6 rounded-2xl border flex flex-col sm:flex-row items-start sm:items-center gap-5 sm:gap-6 ${
                  faixa === 'verde'
                    ? 'bg-[#f6fdf9] border-[#cdeed9] dark:bg-[#10231b] dark:border-[#1e4635]'
                    : faixa === 'ambar'
                      ? 'bg-[#fffdf5] border-[#f6e8b1] dark:bg-[#221c12] dark:border-[#47381b]'
                      : 'bg-[#fffafa] border-[#f7dede] dark:bg-[#21131b] dark:border-[#42202c]'
                }`}
              >
                <AnelNota score={g.score} faixa={faixa} />

                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2 h-2 rounded-full ${
                        faixa === 'verde'
                          ? 'bg-emerald-500'
                          : faixa === 'ambar'
                            ? 'bg-amber-500'
                            : 'bg-[#e11d48]'
                      }`}
                    />
                    <span
                      className={`text-[11px] font-bold tracking-[0.07em] uppercase ${
                        faixa === 'verde'
                          ? 'text-emerald-700 dark:text-emerald-400'
                          : faixa === 'ambar'
                            ? 'text-amber-700 dark:text-amber-400'
                            : 'text-[#be123c] dark:text-[#fb7185]'
                      }`}
                    >
                      {etiquetaHero}
                    </span>
                  </div>

                  <h4 className="text-lg sm:text-[21px] font-extrabold text-[#1e1324] dark:text-white mt-1.5 leading-snug">
                    {tituloHero}
                  </h4>
                  <p className="text-xs sm:text-[13.5px] text-[#5c5166] dark:text-[#c4b8ce] mt-1.5 leading-relaxed">
                    {subtituloHero}
                  </p>
                </div>
              </div>

              {/* 2. Banner Amarelo: Este resultado ainda pode mudar */}
              {g.provisorio && (
                <div className="p-4 sm:p-5 rounded-2xl border bg-[#fefce8] border-[#fde68a] dark:bg-[#231d11] dark:border-[#4d3d1a] flex items-start gap-3.5">
                  <div className="w-9 h-9 rounded-xl bg-[#fef08a]/80 dark:bg-[#382d16] text-[#854d0e] dark:text-amber-300 flex items-center justify-center shrink-0">
                    <Clock className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs sm:text-[13.5px] font-bold text-[#713f12] dark:text-amber-200">
                      Este resultado ainda pode mudar
                    </p>
                    <p className="text-xs sm:text-[13px] text-[#854d0e] dark:text-amber-200/85 mt-1 leading-relaxed">
                      {textoBannerProvisorio}
                    </p>
                  </div>
                </div>
              )}

              {/* 3. Seção: 1. O que você precisa fazer */}
              {cardsAcao.length > 0 && (
                <section className="space-y-3.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="w-6 h-6 rounded-lg bg-[#581c87] text-white text-xs font-bold flex items-center justify-center">
                        1
                      </span>
                      <h4 className="text-sm sm:text-base font-bold text-[#1e1324] dark:text-white">
                        O que você precisa fazer
                      </h4>
                    </div>
                    <span className="px-3 py-1 rounded-full bg-[#f4eff7] dark:bg-[#261a2f] text-xs font-semibold text-[#5c5166] dark:text-[#c4b8ce]">
                      {cardsAcao.length} {cardsAcao.length === 1 ? 'ação' : 'ações'}
                    </span>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 items-stretch">
                    {cardsAcao.map((card) => (
                      <div
                        key={card.chave}
                        className="p-4 sm:p-5 rounded-2xl border border-[#e9e3ee] dark:border-[#2e1f38] bg-white dark:bg-[#1b1222] flex items-start gap-3.5 h-full"
                      >
                        <div
                          className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                            card.cor === 'vermelho'
                              ? 'bg-[#fef2f2] text-[#dc2626] dark:bg-[#2d161e] dark:text-[#f87171]'
                              : 'bg-[#fef9c3]/80 text-[#854d0e] dark:bg-[#2e2412] dark:text-amber-300'
                          }`}
                        >
                          {card.icone === 'arquivo' ? (
                            <FileText className="w-4 h-4" />
                          ) : card.icone === 'relogio' ? (
                            <Clock className="w-4 h-4" />
                          ) : (
                            <AlertTriangle className="w-4 h-4" />
                          )}
                        </div>

                        <div className="min-w-0 flex-1 flex flex-col h-full">
                          <h5 className="text-[13px] sm:text-sm font-bold text-[#1e1324] dark:text-white leading-snug">
                            {card.titulo}
                          </h5>
                          <p className="text-xs sm:text-[13px] text-[#5c5166] dark:text-[#b4a7c0] mt-1.5 leading-relaxed">
                            {card.descricao}
                          </p>
                          <div className="pt-3 mt-auto">
                            <span
                              className={`inline-block px-2.5 py-1 rounded-lg text-[11px] font-bold ${
                                card.cor === 'vermelho'
                                  ? 'bg-[#fef2f2] text-[#b91c1c] dark:bg-[#2d161e] dark:text-[#fca5a5]'
                                  : 'bg-[#fef9c3] text-[#854d0e] dark:bg-[#2e2412] dark:text-amber-300'
                              }`}
                            >
                              {card.badge}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* 4. Acordeão: Entenda como chegamos a esta nota */}
              <div
                ref={acordeaoRef}
                className="rounded-2xl border border-[#e9e3ee] dark:border-[#2e1f38] bg-white dark:bg-[#1b1222] overflow-hidden"
              >
                <button
                  type="button"
                  onClick={() => setDetalhesAbertos((prev) => !prev)}
                  aria-expanded={detalhesAbertos}
                  className="w-full px-5 py-4 flex items-center justify-between gap-4 text-left hover:bg-[#faf8fc] dark:hover:bg-[#211629] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[#9333ea] transition-colors cursor-pointer"
                >
                  <div>
                    <h4 className="text-[13px] sm:text-sm font-bold text-[#1e1324] dark:text-white">
                      Entenda como chegamos a esta nota
                    </h4>
                    <p className="text-xs sm:text-[13px] text-[#6e6378] dark:text-[#b4a7c0] mt-0.5">
                      Veja os critérios, pesos e documentos considerados
                    </p>
                  </div>
                  <span className="p-1.5 rounded-lg text-[#6e6378] dark:text-[#b4a7c0] bg-[#f4eff7] dark:bg-[#261a2f] shrink-0">
                    {detalhesAbertos ? (
                      <ChevronUp className="w-4 h-4" />
                    ) : (
                      <ChevronDown className="w-4 h-4" />
                    )}
                  </span>
                </button>

                {detalhesAbertos && (
                  <div className="px-5 pb-5 pt-4 border-t border-[#efebf3] dark:border-[#261a2e] space-y-4">
                    {/* Os 3 Cards de Critérios com altura e base alinhadas */}
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5 items-stretch">
                      {ORDEM_CRITERIOS.map((chave) => {
                        const c = g.criterios[chave]
                        const calculado = !c.pendente && c.aplicavel && c.nota != null
                        const notaZero = calculado && c.nota === 0
                        const bons = c.bons ?? 0
                        const total = bons + (c.ruins ?? 0)
                        const pesoExibido = Math.round(c.peso_efetivo ?? c.peso)

                        return (
                          <div
                            key={chave}
                            className={`p-4 rounded-xl border flex flex-col justify-between h-full ${
                              notaZero
                                ? 'bg-[#fef6f6] border-[#fadadd] dark:bg-[#26141c] dark:border-[#42202c]'
                                : 'bg-[#f9f7fb] border-[#ece6f2] dark:bg-[#22172a] dark:border-[#31223c]'
                            }`}
                          >
                            <div>
                              <span
                                className={`text-xs font-medium ${
                                  notaZero
                                    ? 'text-[#b91c1c] dark:text-[#fca5a5]'
                                    : 'text-[#6e6378] dark:text-[#b4a7c0]'
                                }`}
                              >
                                {ROTULO_CRITERIO_CARD[chave]}
                              </span>

                              <div
                                className={`text-2xl font-extrabold mt-1.5 ${
                                  notaZero
                                    ? 'text-[#b91c1c] dark:text-[#f87171]'
                                    : 'text-[#1e1324] dark:text-white'
                                }`}
                              >
                                {calculado && c.nota != null ? formatarPercentual(c.nota) : '—'}
                              </div>

                              <div className="text-xs font-semibold text-[#1e1324] dark:text-[#e5dff0] mt-1.5">
                                {calculado
                                  ? CONTAGEM_CURTA[chave](bons, total)
                                  : c.pendente
                                    ? 'Aguardando análise'
                                    : 'Não se aplica'}
                              </div>
                            </div>

                            <div className="text-[11px] text-[#6e6378] dark:text-[#9c8ea6] pt-2.5 mt-2.5 border-t border-black/5 dark:border-white/5">
                              {calculado
                                ? `Peso nesta nota: ${pesoExibido}%`
                                : 'O peso será redistribuído'}
                            </div>
                          </div>
                        )
                      })}
                    </div>

                    {/* Barra de Cálculo Atual */}
                    <div className="p-4 rounded-xl bg-[#f9f7fb] dark:bg-[#22172a] border border-[#ece6f2] dark:border-[#31223c] flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="text-xs sm:text-[13px] font-bold text-[#1e1324] dark:text-white">
                          Cálculo atual
                        </div>
                        <p className="text-xs text-[#6e6378] dark:text-[#b4a7c0] mt-0.5 leading-relaxed">
                          {textoCalculo}
                        </p>
                      </div>
                      <div className="text-sm sm:text-base font-extrabold text-[#4c1d95] dark:text-[#e9d5ff] font-mono shrink-0">
                        {formulaCalculo}
                      </div>
                    </div>

                    {/* Tabela de Documentos Considerados */}
                    <div className="rounded-xl border border-[#ece6f2] dark:border-[#2f203a] overflow-hidden">
                      <div className="px-4 py-3 flex items-center justify-between bg-[#fbf9fc] dark:bg-[#1e1426] border-b border-[#ece6f2] dark:border-[#2f203a]">
                        <span className="text-xs sm:text-[13px] font-bold text-[#1e1324] dark:text-white">
                          Documentos considerados
                        </span>
                        <span className="text-xs font-medium text-[#6e6378] dark:text-[#b4a7c0]">
                          {documentosConsiderados.length}{' '}
                          {documentosConsiderados.length === 1 ? 'tipo' : 'tipos'}
                        </span>
                      </div>

                      <div className="divide-y divide-[#f1ecf6] dark:divide-[#281b32]">
                        {documentosConsiderados.map((doc) => (
                          <div
                            key={doc.tipo}
                            className="px-4 py-3 flex items-center justify-between gap-3 text-xs sm:text-[13px]"
                          >
                            <span className="text-[#2d1f36] dark:text-[#e9e1f0] font-medium truncate">
                              {doc.nome}
                            </span>

                            {doc.statusTipo === 'analise' ? (
                              <span className="inline-flex items-center gap-1.5 font-semibold text-[#854d0e] dark:text-amber-300 shrink-0">
                                <Clock className="w-3.5 h-3.5" />
                                <span>{doc.statusLabel}</span>
                              </span>
                            ) : doc.statusTipo === 'enviado' ? (
                              <span className="inline-flex items-center gap-1.5 font-semibold text-emerald-700 dark:text-emerald-400 shrink-0">
                                <Check className="w-3.5 h-3.5" />
                                <span>{doc.statusLabel}</span>
                              </span>
                            ) : (
                              <span className="font-semibold text-[#b91c1c] dark:text-[#f87171] shrink-0">
                                {doc.statusLabel}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* Nota de Rodapé Interna */}
                    <div className="flex items-start sm:items-center gap-2 text-xs text-[#6e6378] dark:text-[#b4a7c0] pt-1">
                      <Info className="w-4 h-4 shrink-0 mt-0.5 sm:mt-0" />
                      <span>
                        Esta nota avalia se a empresa possui a documentação obrigatória. Ela não
                        mede o risco de falha de ponto.
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Rodapé do Modal */}
        <div className="px-6 sm:px-8 py-4 border-t border-[#efebf3] dark:border-[#25192e] bg-[#fbf9fc] dark:bg-[#130c18] flex items-center justify-between gap-4">
          <div className="flex items-center gap-2 text-xs sm:text-[13px] text-[#5c5166] dark:text-[#b4a7c0]">
            <Check className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <span>A nota é recalculada automaticamente após cada análise.</span>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="px-6 py-2.5 rounded-xl bg-[#581c87] hover:bg-[#6b21a8] dark:bg-[#7e22ce] dark:hover:bg-[#9333ea] text-white text-xs sm:text-sm font-bold shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#9333ea] transition-colors cursor-pointer shrink-0"
          >
            Entendi
          </button>
        </div>
      </div>
    </div>
  )
}

export default ConformidadeEmpresaModal
