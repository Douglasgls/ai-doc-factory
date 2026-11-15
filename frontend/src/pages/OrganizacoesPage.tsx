import React, { useCallback, useEffect, useState } from 'react'
import { Briefcase, Building2, ChevronRight, FileText, Loader2, Plus } from 'lucide-react'
import {
  apiService,
  type ConviteCriado,
  type Contrato,
  type Prestador,
  type Tomador,
} from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { extraEmailClasses, validarEmail } from '../utils/convites'
import { BTN_SEC, CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL, TD, TH } from '../components/formUi'
import { ConviteLink } from '../components/ConviteLink'
import { CadastroTerceirizadaForm } from '../components/CadastroTerceirizadaForm'
import {
  AcessoSelo,
  ConviteGeradoCard,
  ReenvioBotao,
  ReenvioLinha,
} from '../components/ReenvioConvite'
import { useReenvioConvite } from '../hooks/useReenvioConvite'

type Aba = 'contratos' | 'tomadores' | 'prestadores'

const Situacao: React.FC<{ ativo: boolean }> = ({ ativo }) => (
  <span
    className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${
      ativo
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    }`}
  >
    {ativo ? 'Ativo' : 'Inativo'}
  </span>
)

function formatData(iso: string | null): string {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

interface OrganizacoesPageProps {
  onBack: () => void
}

const OrganizacoesPage: React.FC<OrganizacoesPageProps> = ({ onBack }) => {
  const [aba, setAba] = useState<Aba>('contratos')
  const [tomadores, setTomadores] = useState<Tomador[]>([])
  const [prestadores, setPrestadores] = useState<Prestador[]>([])
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [tomNome, setTomNome] = useState('')
  const [tomCnpj, setTomCnpj] = useState('')
  const [prestCnpj, setPrestCnpj] = useState('')
  const [prestRazao, setPrestRazao] = useState('')

  // Logo após criar um tomador: convite do primeiro administrador do cliente
  const [tomNovo, setTomNovo] = useState<Tomador | null>(null)
  const [convEmail, setConvEmail] = useState('')
  const [convSaving, setConvSaving] = useState(false)
  const [convError, setConvError] = useState<string | null>(null)
  const [convCriado, setConvCriado] = useState<ConviteCriado | null>(null)

  const convEmailValido = validarEmail(convEmail)

  const carregar = useCallback(async () => {
    try {
      const [t, p, c] = await Promise.all([
        apiService.getTomadores(),
        apiService.getPrestadores(),
        apiService.getContratos(),
      ])
      setTomadores(t)
      setPrestadores(p)
      setContratos(c)
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Erro ao carregar organizações')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void carregar(), 0)
    return () => clearTimeout(timer)
  }, [carregar])

  const trocarAba = (nova: Aba) => {
    setAba(nova)
    setFormError(null)
  }

  const enviar = async (e: React.FormEvent, acao: () => Promise<void>) => {
    e.preventDefault()
    setFormError(null)
    setSaving(true)
    try {
      await acao()
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const salvarTomador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (tomCnpj && !isCnpjValido(tomCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      const novo = await apiService.createTomador({ nome: tomNome, cnpj: tomCnpj || null })
      setTomNome('')
      setTomCnpj('')
      setTomNovo(novo)
      setConvEmail('')
      setConvError(null)
      setConvCriado(null)
    })

  const convidarAdminCliente = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!tomNovo) return
    if (!validarEmail(convEmail)) {
      setConvError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setConvError(null)
    setConvSaving(true)
    try {
      setConvCriado(
        await apiService.criarConvite({
          email: convEmail.trim(),
          nivel: 'tomador',
          papel: 'admin',
          tomador_id: tomNovo.id,
        })
      )
      setConvEmail('')
    } catch (err) {
      setConvError(err instanceof Error ? err.message : 'Erro ao criar convite')
    } finally {
      setConvSaving(false)
    }
  }

  const salvarPrestador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (!isCnpjValido(prestCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      await apiService.createPrestador({ cnpj: prestCnpj, razao_social: prestRazao })
      setPrestCnpj('')
      setPrestRazao('')
    })

  const reenvio = useReenvioConvite(carregar)

  const abasInfo: {
    id: Aba
    label: string
    subtitulo: string
    icon: React.ComponentType<{ className?: string }>
    count: number
  }[] = [
    {
      id: 'contratos',
      label: 'Contratos',
      subtitulo: 'Vincule uma empresa prestadora a um tomador.',
      icon: FileText,
      count: contratos.length,
    },
    {
      id: 'tomadores',
      label: 'Tomadores',
      subtitulo: 'Cadastre as empresas que contratam os serviços.',
      icon: Building2,
      count: tomadores.length,
    },
    {
      id: 'prestadores',
      label: 'Prestadores',
      subtitulo: 'Cadastre as empresas que executam os serviços.',
      icon: Briefcase,
      count: prestadores.length,
    },
  ]

  return (
    <div className="space-y-6">
      {/* Breadcrumb de navegação */}
      <nav className="flex items-center gap-2 text-xs sm:text-sm text-[#877991] dark:text-[#95849f]">
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer inline-flex items-center gap-1.5"
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Documentos</span>
        </button>
        <ChevronRight className="w-3.5 h-3.5 opacity-60" />
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Organizações</span>
      </nav>

      {/* Cabeçalho estilizado */}
      <div className="flex items-start sm:items-center gap-3.5">
        <div className="w-11 h-11 rounded-2xl bg-purple-950/40 border border-purple-800/40 flex items-center justify-center text-purple-400 shrink-0 shadow-sm mt-0.5 sm:mt-0">
          <Building2 className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-[#2d0a33] dark:text-white tracking-tight">
            Organizações e contratos
          </h1>
          <p className="text-xs sm:text-sm text-[#877991] dark:text-[#a093a8] mt-0.5">
            Gerencie tomadores, prestadores e os vínculos de serviço entre as empresas.
          </p>
        </div>
      </div>

      {/* 3 Cards de Estatísticas e Abas */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {abasInfo.map((item) => {
          const Icon = item.icon
          const ativo = aba === item.id
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => trocarAba(item.id)}
              className={`text-left p-4 rounded-2xl transition-all cursor-pointer relative flex flex-col justify-between ${
                ativo
                  ? 'bg-[#22102c] border-2 border-[#a816be] shadow-[0_0_20px_rgba(168,22,190,0.18)]'
                  : 'bg-white dark:bg-[#160c20]/70 border border-[#ebe5ef] dark:border-[#2f1e39] hover:border-[#6b21a8] hover:dark:border-[#4a2656]'
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0">
                  <div
                    className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 ${
                      ativo
                        ? 'bg-purple-900/40 text-[#f38df9]'
                        : 'bg-purple-100 dark:bg-purple-950/40 text-purple-600 dark:text-purple-400'
                    }`}
                  >
                    <Icon className="w-5 h-5" />
                  </div>
                  <div className="min-w-0">
                    <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white truncate">
                      {item.label}
                    </h3>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5 line-clamp-1">
                      {item.subtitulo}
                    </p>
                  </div>
                </div>
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-bold shrink-0 ${
                    ativo
                      ? 'bg-purple-900/50 text-white border border-purple-700/50'
                      : 'bg-slate-100 dark:bg-[#25152e] text-slate-600 dark:text-[#c4b5cd]'
                  }`}
                >
                  {item.count}
                </span>
              </div>
            </button>
          )
        })}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />

          {/* ABA: TOMADORES */}
          {aba === 'tomadores' && (
            <>
              <form onSubmit={salvarTomador} className={`${CARD} p-6 space-y-5`} aria-label="Cadastrar tomador">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-4">
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-[#d946ef]">
                      NOVO CADASTRO
                    </span>
                    <h3 className="text-base sm:text-lg font-bold text-[#2d0a33] dark:text-white mt-0.5">
                      Cadastrar tomador
                    </h3>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                      Cadastre as empresas que contratam os serviços da sua plataforma.
                    </p>
                  </div>
                  <span className="text-xs text-[#877991] dark:text-[#95849f] self-start sm:self-auto">
                    * Campos obrigatórios
                  </span>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="tom-nome" className={LABEL}>
                      Nome do tomador *
                    </label>
                    <input
                      id="tom-nome"
                      className={INPUT}
                      value={tomNome}
                      required
                      placeholder="Ex.: Alpha Empreendimentos"
                      onChange={(e) => setTomNome(e.target.value)}
                    />
                  </div>
                  <div>
                    <label htmlFor="tom-cnpj" className={LABEL}>
                      CNPJ (opcional)
                    </label>
                    <input
                      id="tom-cnpj"
                      className={INPUT}
                      value={tomCnpj}
                      placeholder="00.000.000/0000-00"
                      inputMode="numeric"
                      onChange={(e) => setTomCnpj(maskCnpj(e.target.value))}
                    />
                  </div>
                </div>

                <ErroBox message={formError} />

                <button
                  type="submit"
                  disabled={saving || !tomNome.trim()}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#a816be] hover:bg-[#bd19d6] transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Cadastrar tomador
                </button>
              </form>

              {tomNovo && (
                <form
                  onSubmit={convidarAdminCliente}
                  className={`${CARD} p-6 space-y-4`}
                  aria-label="Convidar administrador do cliente"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-3">
                    <div>
                      <span className="text-[11px] font-bold uppercase tracking-wider text-[#d946ef]">
                        ACESSO INICIAL
                      </span>
                      <h3 className="text-base font-bold text-[#2d0a33] dark:text-white mt-0.5">
                        Convidar administrador do tomador: {tomNovo.nome}
                      </h3>
                      <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                        Envie o primeiro convite de acesso para o administrador deste cliente.
                      </p>
                    </div>
                    <button
                      type="button"
                      className={BTN_SEC}
                      onClick={() => setTomNovo(null)}
                    >
                      Fechar
                    </button>
                  </div>

                  {!convCriado && (
                    <div>
                      <label htmlFor="conv-adm-email" className={LABEL}>
                        E-mail do administrador *
                      </label>
                      <input
                        id="conv-adm-email"
                        type="email"
                        className={`${INPUT} ${extraEmailClasses(convEmail, convEmailValido)}`}
                        value={convEmail}
                        required
                        aria-invalid={convEmail.trim().length > 0 && !convEmailValido}
                        aria-describedby="conv-adm-email-feedback"
                        onChange={(e) => {
                          setConvEmail(e.target.value)
                          if (convError) setConvError(null)
                        }}
                        placeholder="administrador@cliente.com.br"
                      />
                      <span className="block text-[11px] text-[#877991] dark:text-[#95849f] mt-1">
                        Usado para enviar o acesso inicial.
                      </span>
                      <EmailStatusFeedback email={convEmail} valido={convEmailValido} id="conv-adm-email-feedback" />
                    </div>
                  )}

                  <ErroBox message={convError} />

                  {convCriado ? (
                    <ConviteLink
                      token={convCriado.token}
                      expiraEm={convCriado.expira_em}
                      email={convCriado.email}
                      papel={convCriado.papel}
                    />
                  ) : (
                    <button
                      type="submit"
                      disabled={convSaving || !convEmailValido}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#a816be] hover:bg-[#bd19d6] transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {convSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                      Convidar administrador do cliente
                    </button>
                  )}
                </form>
              )}

              {/* Tabela oficial de Tomadores */}
              <div className={`${CARD} overflow-hidden`}>
                <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Tomadores cadastrados
                  </h3>
                  <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                    {tomadores.length} {tomadores.length === 1 ? 'tomador' : 'tomadores'}
                  </p>
                </div>

                {tomadores.length === 0 ? (
                  <div className="py-14 text-center flex flex-col items-center justify-center px-4">
                    <div className="w-12 h-12 rounded-2xl bg-[#2a1333] border border-[#4a1c59] flex items-center justify-center text-[#d946ef] mb-3 shadow-inner">
                      <Building2 className="w-6 h-6" />
                    </div>
                    <h4 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                      Nenhum tomador cadastrado
                    </h4>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] max-w-sm mt-1">
                      Cadastre o primeiro tomador no formulário acima para começar a gerenciar contratos.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    <table className="w-full text-left border-collapse min-w-[500px]">
                      <thead>
                        <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                          <th className={TH}>Nome</th>
                          <th className={TH}>CNPJ</th>
                          <th className={TH}>Situação</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                        {tomadores.map((t) => (
                          <tr key={t.id} className="hover:bg-slate-50/50 dark:hover:bg-[#23152c]/50 transition-colors">
                            <td className={`${TD} font-bold`}>{t.nome}</td>
                            <td className={`${TD} font-mono`}>{formatCnpj(t.cnpj) || '—'}</td>
                            <td className={TD}><Situacao ativo={t.ativo} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ABA: PRESTADORES */}
          {aba === 'prestadores' && (
            <>
              <form onSubmit={salvarPrestador} className={`${CARD} p-6 space-y-5`} aria-label="Cadastrar prestador">
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-4">
                  <div>
                    <span className="text-[11px] font-bold uppercase tracking-wider text-[#d946ef]">
                      NOVO CADASTRO
                    </span>
                    <h3 className="text-base sm:text-lg font-bold text-[#2d0a33] dark:text-white mt-0.5">
                      Cadastrar prestador
                    </h3>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                      Cadastre as empresas que executam os serviços para seus clientes.
                    </p>
                  </div>
                  <span className="text-xs text-[#877991] dark:text-[#95849f] self-start sm:self-auto">
                    * Campos obrigatórios
                  </span>
                </div>

                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="prest-cnpj" className={LABEL}>
                      CNPJ do prestador *
                    </label>
                    <input
                      id="prest-cnpj"
                      className={INPUT}
                      value={prestCnpj}
                      required
                      placeholder="00.000.000/0000-00"
                      inputMode="numeric"
                      onChange={(e) => setPrestCnpj(maskCnpj(e.target.value))}
                    />
                  </div>
                  <div>
                    <label htmlFor="prest-razao" className={LABEL}>
                      Razão social do prestador *
                    </label>
                    <input
                      id="prest-razao"
                      className={INPUT}
                      value={prestRazao}
                      required
                      placeholder="Ex.: Serviços Horizonte Ltda."
                      onChange={(e) => setPrestRazao(e.target.value)}
                    />
                  </div>
                </div>

                <ErroBox message={formError} />

                <button
                  type="submit"
                  disabled={saving || !prestRazao.trim() || !prestCnpj}
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#a816be] hover:bg-[#bd19d6] transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  Cadastrar prestador
                </button>
              </form>

              {/* Tabela oficial de Prestadores */}
              <div className={`${CARD} overflow-hidden`}>
                <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Prestadores cadastrados
                  </h3>
                  <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                    {prestadores.length} {prestadores.length === 1 ? 'prestador' : 'prestadores'}
                  </p>
                </div>

                {prestadores.length === 0 ? (
                  <div className="py-14 text-center flex flex-col items-center justify-center px-4">
                    <div className="w-12 h-12 rounded-2xl bg-[#2a1333] border border-[#4a1c59] flex items-center justify-center text-[#d946ef] mb-3 shadow-inner">
                      <Briefcase className="w-6 h-6" />
                    </div>
                    <h4 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                      Nenhum prestador cadastrado
                    </h4>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] max-w-sm mt-1">
                      Cadastre a primeira empresa prestadora no formulário acima para vincular aos contratos.
                    </p>
                  </div>
                ) : (
                  <div className="overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    <table className="w-full text-left border-collapse min-w-[500px]">
                      <thead>
                        <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                          <th className={TH}>Razão social</th>
                          <th className={TH}>CNPJ</th>
                          <th className={TH}>Situação</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                        {prestadores.map((p) => (
                          <tr key={p.id} className="hover:bg-slate-50/50 dark:hover:bg-[#23152c]/50 transition-colors">
                            <td className={`${TD} font-bold`}>{p.razao_social}</td>
                            <td className={`${TD} font-mono`}>{formatCnpj(p.cnpj)}</td>
                            <td className={TD}><Situacao ativo={p.ativo} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}

          {/* ABA: CONTRATOS */}
          {aba === 'contratos' && (
            <>
              <CadastroTerceirizadaForm
                titulo="Cadastrar contrato de prestação"
                subtitulo="Vincule uma empresa prestadora ao tomador responsável pelo contrato."
                tomadores={tomadores}
                onCadastrada={carregar}
                onTrocarAbaTomadores={() => trocarAba('tomadores')}
              />

              <ConviteGeradoCard reenvio={reenvio} />

              {/* Tabela oficial de Contratos */}
              <div className={`${CARD} overflow-hidden`}>
                <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Contratos cadastrados
                  </h3>
                  <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
                    {contratos.length} {contratos.length === 1 ? 'contrato' : 'contratos'}
                  </p>
                </div>

                {contratos.length === 0 ? (
                  <div className="py-14 text-center flex flex-col items-center justify-center px-4">
                    <div className="w-12 h-12 rounded-2xl bg-[#2a1333] border border-[#4a1c59] flex items-center justify-center text-[#d946ef] mb-3 shadow-inner">
                      <FileText className="w-6 h-6" />
                    </div>
                    <h4 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                      Nenhum contrato cadastrado
                    </h4>
                    <p className="text-xs text-[#877991] dark:text-[#a093a8] max-w-sm mt-1">
                      Cadastre um tomador e depois crie o primeiro vínculo com uma empresa prestadora.
                    </p>
                    <button
                      type="button"
                      onClick={() => trocarAba('tomadores')}
                      className="mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-[#2a1333] hover:bg-[#381a44] text-[#d946ef] border border-[#4a1c59] transition-colors cursor-pointer"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      Cadastrar tomador
                    </button>
                  </div>
                ) : (
                  <div className="overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
                    <table className="w-full text-left border-collapse min-w-[700px]">
                      <thead>
                        <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                          <th className={TH}>Tomador</th>
                          <th className={TH}>Prestador</th>
                          <th className={TH}>CNPJ</th>
                          <th className={TH}>Vigência</th>
                          <th className={TH}>Situação</th>
                          <th className={TH}>Acesso</th>
                          <th className={TH}></th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                        {contratos.map((c) => (
                          <React.Fragment key={c.id}>
                            <tr className="hover:bg-slate-50/50 dark:hover:bg-[#23152c]/50 transition-colors">
                              <td className={`${TD} font-bold`}>{c.tomador_nome}</td>
                              <td className={TD}>{c.prestador_razao_social}</td>
                              <td className={`${TD} font-mono`}>{formatCnpj(c.prestador_cnpj)}</td>
                              <td className={TD}>
                                {c.vigencia_inicio || c.vigencia_fim
                                  ? `${formatData(c.vigencia_inicio)} a ${formatData(c.vigencia_fim)}`
                                  : '—'}
                              </td>
                              <td className={TD}><Situacao ativo={c.ativo} /></td>
                              <td className={TD}><AcessoSelo contrato={c} /></td>
                              <td className={TD}><ReenvioBotao contrato={c} reenvio={reenvio} /></td>
                            </tr>
                            <ReenvioLinha contrato={c} reenvio={reenvio} colSpan={7} />
                          </React.Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default OrganizacoesPage
