import React, { useCallback, useEffect, useState } from 'react'
import { Eye, Loader2, Mail, Send, ShieldCheck, User, Users, X } from 'lucide-react'
import {
  apiService,
  type ConviteCriado,
  type ConviteListado,
  type NovoConvite,
  type UsuarioAtual,
  type UsuarioListado,
} from '../services/api'
import {
  ESTADO_CONVITE,
  extraEmailClasses,
  extrairIniciais,
  formatDataHoraCurta,
  formatDataHoraPorExtenso,
  NIVEL_ROTULO,
  PAPEL_ROTULO,
  validarEmail,
} from '../utils/convites'
import { CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL, Selo } from '../components/formUi'
import { ConviteLink } from '../components/ConviteLink'

interface EquipePageProps {
  usuario: UsuarioAtual
  onBack: () => void
}

const TH_COMPACT = 'px-2.5 py-2.5 text-[10px] sm:text-[11px] font-bold text-[#6e6378] dark:text-[#a093a8] uppercase tracking-wider'
const TD_COMPACT = 'px-2.5 py-2.5 text-xs text-[#2d0a33] dark:text-[#f8f5fc]'

/** Convite de colega: nível e organização são os do próprio usuário (plataforma convida plataforma). */
function conviteParaColega(usuario: UsuarioAtual, email: string, papel: 'admin' | 'membro'): NovoConvite {
  if (usuario.nivel === 'tomador') return { email, nivel: 'tomador', papel, tomador_id: usuario.tomador_id }
  if (usuario.nivel === 'prestador') return { email, nivel: 'prestador', papel, prestador_id: usuario.prestador_id }
  return { email, nivel: 'plataforma', papel }
}

const EquipePage: React.FC<EquipePageProps> = ({ usuario, onBack }) => {
  const [usuarios, setUsuarios] = useState<UsuarioListado[]>([])
  const [convites, setConvites] = useState<ConviteListado[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [email, setEmail] = useState('')
  const [papel, setPapel] = useState<'admin' | 'membro'>('membro')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [criado, setCriado] = useState<ConviteCriado | null>(null)

  // Modais de detalhes para inspeção individual sem necessidade de scroll horizontal
  const [conviteDetalhes, setConviteDetalhes] = useState<ConviteListado | null>(null)
  const [usuarioDetalhes, setUsuarioDetalhes] = useState<UsuarioListado | null>(null)

  const emailValido = validarEmail(email)

  const carregar = useCallback(async () => {
    try {
      const [u, c] = await Promise.all([apiService.getUsuarios(), apiService.getConvites()])
      setUsuarios(u)
      setConvites(c)
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Erro ao carregar a equipe')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void carregar(), 0)
    return () => clearTimeout(timer)
  }, [carregar])

  const convidar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!validarEmail(email)) {
      setFormError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setFormError(null)
    setCriado(null)
    setSaving(true)
    try {
      const novoConvite = await apiService.criarConvite(conviteParaColega(usuario, email.trim(), papel))
      setCriado(novoConvite)
      setEmail('')
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao criar convite')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      {/* Navegação / Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button onClick={onBack} className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer">
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Equipe</span>
      </nav>

      {/* Cabeçalho da página */}
      <div className="flex items-center gap-3.5">
        <div className="w-11 h-11 rounded-2xl bg-purple-100 dark:bg-purple-950/60 text-[#9333ea] dark:text-[#f38df9] flex items-center justify-center shrink-0 border border-purple-200/60 dark:border-purple-800/40 shadow-xs">
          <Users className="w-5 h-5" />
        </div>
        <div>
          <h1 className="text-xl sm:text-2xl font-bold text-[#2d0a33] dark:text-white tracking-tight">
            Equipe e acessos
          </h1>
          <p className="text-xs sm:text-sm text-[#6e6378] dark:text-[#a093a8]">
            Convide pessoas e acompanhe quem pode acessar os documentos da organização.
          </p>
        </div>
      </div>

      {/* Card Novo Acesso */}
      <form onSubmit={convidar} className={`${CARD} p-6 space-y-5`} aria-label="Convidar uma pessoa">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-4">
          <div>
            <span className="text-[11px] font-bold tracking-wider uppercase text-purple-600 dark:text-purple-400">
              NOVO ACESSO
            </span>
            <h3 className="text-base font-bold text-[#2d0a33] dark:text-white mt-0.5">
              Convidar uma pessoa
            </h3>
            <p className="text-xs text-[#6e6378] dark:text-[#a093a8]">
              Informe o e-mail e escolha o que a pessoa poderá fazer no sistema.
            </p>
          </div>
          <div className="self-start sm:self-auto inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/40 border border-purple-200 dark:border-purple-800/40">
            <ShieldCheck className="w-3.5 h-3.5 text-purple-500 shrink-0" />
            <span>Convite individual e temporário</span>
          </div>
        </div>

        {/* Linha dos campos e botão alinhados */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-12 items-start">
          <div className="lg:col-span-6">
            <label htmlFor="eq-email" className={LABEL}>E-mail da pessoa *</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-[#8f8298] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="eq-email"
                type="email"
                className={`${INPUT} pl-9 h-[42px] ${extraEmailClasses(email, emailValido)}`}
                value={email}
                required
                aria-invalid={email.trim().length > 0 && !emailValido}
                aria-describedby="eq-email-feedback"
                onChange={(e) => {
                  setEmail(e.target.value)
                  if (formError) setFormError(null)
                }}
                placeholder="douglaspaz955@gmail.com"
              />
            </div>
            <div className="mt-1.5 min-h-[18px]">
              <EmailStatusFeedback email={email} valido={emailValido} id="eq-email-feedback" />
            </div>
          </div>

          <div className="lg:col-span-4">
            <label htmlFor="eq-papel" className={LABEL}>Tipo de acesso</label>
            <div className="relative">
              <User className="w-4 h-4 text-[#8f8298] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <select
                id="eq-papel"
                className={`${INPUT} pl-9 h-[42px]`}
                value={papel}
                onChange={(e) => setPapel(e.target.value as 'admin' | 'membro')}
              >
                <option value="membro">Membro</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
            <div className="mt-1.5 min-h-[18px]">
              <p className="text-[11px] text-[#6e6378] dark:text-[#a093a8] leading-tight">
                {papel === 'membro'
                  ? 'Pode acessar e trabalhar com os documentos da organização.'
                  : 'Acesso total à administração e documentos da organização.'}
              </p>
            </div>
          </div>

          <div className="lg:col-span-2 sm:col-span-2">
            <label className="block text-xs font-semibold invisible mb-1 select-none" aria-hidden="true">
              Ação
            </label>
            <button
              type="submit"
              disabled={saving || !emailValido}
              className="w-full h-[42px] px-4 rounded-xl text-sm font-bold text-white bg-[#a816be] hover:bg-[#bd19d6] disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-all active:scale-95"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Criar convite
            </button>
            <div className="mt-1.5 min-h-[18px]" aria-hidden="true" />
          </div>
        </div>

        <ErroBox message={formError} />

        {/* Card do token/link criado em tom de verde de sucesso */}
        {criado && (
          <ConviteLink
            token={criado.token}
            expiraEm={criado.expira_em}
            email={criado.email}
            papel={criado.papel}
          />
        )}
      </form>

      {/* Seção das Tabelas */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />
          <div className="grid gap-6 lg:grid-cols-2 items-start">
            {/* Tabela de Usuários / Pessoas com acesso */}
            <div className={`${CARD} overflow-hidden flex flex-col`}>
              <div className="p-4 sm:p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Pessoas com acesso
                  </h3>
                  <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                    Usuários que já podem entrar na organização.
                  </p>
                </div>
                <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 shrink-0">
                  {usuarios.length} {usuarios.length === 1 ? 'pessoa' : 'pessoas'}
                </span>
              </div>
              <div className="overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH_COMPACT}>Nome</th>
                      <th className={TH_COMPACT}>E-mail</th>
                      <th className={TH_COMPACT}>Nível</th>
                      <th className={TH_COMPACT}>Papel</th>
                      <th className={TH_COMPACT}>Situação</th>
                      <th className={`${TH_COMPACT} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {usuarios.map((u) => (
                      <tr key={u.id} className="hover:bg-purple-50/30 dark:hover:bg-purple-950/10 transition-colors">
                        <td className={TD_COMPACT}>
                          <div className="flex items-center gap-2 max-w-[110px] sm:max-w-[140px]">
                            <div className="w-6 h-6 rounded-md bg-[#3e1347] dark:bg-[#34163d] text-[#e87bf8] dark:text-[#f38df9] font-bold text-[10px] flex items-center justify-center shrink-0">
                              {extrairIniciais(u.nome)}
                            </div>
                            <span className="font-semibold text-[#2d0a33] dark:text-white truncate" title={u.nome}>
                              {u.nome}
                            </span>
                          </div>
                        </td>
                        <td className={TD_COMPACT}>
                          <span className="block max-w-[110px] sm:max-w-[130px] truncate" title={u.email}>
                            {u.email}
                          </span>
                        </td>
                        <td className={TD_COMPACT}>{NIVEL_ROTULO[u.nivel] ?? u.nivel}</td>
                        <td className={TD_COMPACT}>{PAPEL_ROTULO[u.papel] ?? u.papel}</td>
                        <td className={TD_COMPACT}>
                          <Selo tom={u.ativo ? 'verde' : 'cinza'}>
                            {u.ativo ? 'Ativo' : 'Inativo'}
                          </Selo>
                        </td>
                        <td className={`${TD_COMPACT} text-right`}>
                          <button
                            type="button"
                            onClick={() => setUsuarioDetalhes(u)}
                            title="Visualizar detalhes do usuário"
                            className="p-1 rounded-md text-[#877991] hover:text-[#9333ea] dark:hover:text-[#f38df9] hover:bg-purple-100 dark:hover:bg-purple-950/60 transition-colors cursor-pointer"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {usuarios.length === 0 && (
                      <tr>
                        <td className={TD_COMPACT} colSpan={6}>Nenhum usuário cadastrado.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Tabela de Convites aguardando resposta */}
            <div className={`${CARD} overflow-hidden flex flex-col`}>
              <div className="p-4 sm:p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Convites aguardando resposta
                  </h3>
                  <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                    Pessoas que ainda não aceitaram o convite.
                  </p>
                </div>
                <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 shrink-0">
                  {convites.length} {convites.length === 1 ? 'convite' : 'convites'}
                </span>
              </div>
              <div className="overflow-x-auto [scrollbar-width:none] [-ms-overflow-style:none] [&::-webkit-scrollbar]:hidden">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH_COMPACT}>E-mail</th>
                      <th className={TH_COMPACT}>Organização</th>
                      <th className={TH_COMPACT}>Papel</th>
                      <th className={TH_COMPACT}>Situação</th>
                      <th className={TH_COMPACT}>Válido até</th>
                      <th className={`${TH_COMPACT} w-8`}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {convites.map((c) => (
                      <tr key={c.id} className="hover:bg-purple-50/30 dark:hover:bg-purple-950/10 transition-colors">
                        <td className={TD_COMPACT}>
                          <span
                            className="block font-semibold text-[#2d0a33] dark:text-white max-w-[110px] sm:max-w-[140px] truncate"
                            title={c.email}
                          >
                            {c.email}
                          </span>
                        </td>
                        <td className={TD_COMPACT}>
                          <span
                            className="block max-w-[75px] sm:max-w-[90px] truncate text-[#6e6378] dark:text-[#a093a8]"
                            title={c.organizacao_nome ?? NIVEL_ROTULO[c.nivel] ?? c.nivel}
                          >
                            {c.organizacao_nome ?? NIVEL_ROTULO[c.nivel] ?? c.nivel}
                          </span>
                        </td>
                        <td className={TD_COMPACT}>{PAPEL_ROTULO[c.papel] ?? c.papel}</td>
                        <td className={TD_COMPACT}>
                          <Selo tom={c.estado === 'usado' ? 'verde' : c.estado === 'pendente' ? 'ambar' : 'cinza'}>
                            {c.estado === 'pendente' ? 'Aguardando resposta' : ESTADO_CONVITE[c.estado] ?? c.estado}
                          </Selo>
                        </td>
                        <td className={`${TD_COMPACT} whitespace-nowrap text-[11px] text-[#6e6378] dark:text-[#a093a8]`}>
                          {formatDataHoraCurta(c.expira_em)}
                        </td>
                        <td className={`${TD_COMPACT} text-right`}>
                          <button
                            type="button"
                            onClick={() => setConviteDetalhes(c)}
                            title="Visualizar detalhes do convite"
                            className="p-1 rounded-md text-[#877991] hover:text-[#9333ea] dark:hover:text-[#f38df9] hover:bg-purple-100 dark:hover:bg-purple-950/60 transition-colors cursor-pointer"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                    {convites.length === 0 && (
                      <tr>
                        <td className={TD_COMPACT} colSpan={6}>Nenhum convite pendente.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Modal de Detalhes do Convite (acessado pelo olhinho) */}
      {conviteDetalhes && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-md rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-purple-100 dark:bg-purple-950/60 text-purple-600 dark:text-purple-300 flex items-center justify-center">
                  <Mail className="w-4 h-4" />
                </div>
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                  Detalhes do convite
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setConviteDetalhes(null)}
                className="p-1 rounded-lg text-[#877991] hover:text-[#2d0a33] dark:hover:text-white hover:bg-[#f4e8f7] dark:hover:bg-[#34163d] transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">E-mail:</span>
                <span className="font-semibold text-sm text-[#2d0a33] dark:text-white break-all">
                  {conviteDetalhes.email}
                </span>
              </div>
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Organização:</span>
                  <span className="text-[#2d0a33] dark:text-[#f8f5fc] font-medium">
                    {conviteDetalhes.organizacao_nome ?? NIVEL_ROTULO[conviteDetalhes.nivel] ?? conviteDetalhes.nivel}
                  </span>
                </div>
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Papel:</span>
                  <span className="text-[#2d0a33] dark:text-[#f8f5fc] font-medium">
                    {PAPEL_ROTULO[conviteDetalhes.papel] ?? conviteDetalhes.papel}
                  </span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Situação:</span>
                  <Selo tom={conviteDetalhes.estado === 'usado' ? 'verde' : conviteDetalhes.estado === 'pendente' ? 'ambar' : 'cinza'}>
                    {conviteDetalhes.estado === 'pendente' ? 'Aguardando resposta' : ESTADO_CONVITE[conviteDetalhes.estado] ?? conviteDetalhes.estado}
                  </Selo>
                </div>
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Válido até:</span>
                  <span className="text-[#2d0a33] dark:text-[#f8f5fc] font-medium">
                    {formatDataHoraPorExtenso(conviteDetalhes.expira_em)}
                  </span>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setConviteDetalhes(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-[#5c1363] dark:text-[#f38df9] bg-[#f4e8f7] dark:bg-[#34163d] hover:opacity-80 transition-all cursor-pointer"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal de Detalhes do Usuário (acessado pelo olhinho) */}
      {usuarioDetalhes && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-150">
          <div className="w-full max-w-md rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-3">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-[#3e1347] dark:bg-[#34163d] text-[#e87bf8] dark:text-[#f38df9] font-bold text-xs flex items-center justify-center">
                  {extrairIniciais(usuarioDetalhes.nome)}
                </div>
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                  Detalhes do usuário
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setUsuarioDetalhes(null)}
                className="p-1 rounded-lg text-[#877991] hover:text-[#2d0a33] dark:hover:text-white hover:bg-[#f4e8f7] dark:hover:bg-[#34163d] transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Nome:</span>
                <span className="font-semibold text-sm text-[#2d0a33] dark:text-white">
                  {usuarioDetalhes.nome}
                </span>
              </div>
              <div>
                <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">E-mail:</span>
                <span className="text-[#2d0a33] dark:text-[#f8f5fc] break-all font-medium">
                  {usuarioDetalhes.email}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 pt-1">
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Nível:</span>
                  <span className="text-[#2d0a33] dark:text-[#f8f5fc]">
                    {NIVEL_ROTULO[usuarioDetalhes.nivel] ?? usuarioDetalhes.nivel}
                  </span>
                </div>
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Papel:</span>
                  <span className="text-[#2d0a33] dark:text-[#f8f5fc]">
                    {PAPEL_ROTULO[usuarioDetalhes.papel] ?? usuarioDetalhes.papel}
                  </span>
                </div>
                <div>
                  <span className="text-[#877991] dark:text-[#95849f] font-medium block mb-0.5">Situação:</span>
                  <Selo tom={usuarioDetalhes.ativo ? 'verde' : 'cinza'}>
                    {usuarioDetalhes.ativo ? 'Ativo' : 'Inativo'}
                  </Selo>
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                type="button"
                onClick={() => setUsuarioDetalhes(null)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-[#5c1363] dark:text-[#f38df9] bg-[#f4e8f7] dark:bg-[#34163d] hover:opacity-80 transition-all cursor-pointer"
              >
                Fechar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default EquipePage
