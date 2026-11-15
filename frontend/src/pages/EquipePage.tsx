import React, { useCallback, useEffect, useState } from 'react'
import { Loader2, Mail, Send, ShieldCheck, User, Users } from 'lucide-react'
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
  formatDataHora,
  NIVEL_ROTULO,
  PAPEL_ROTULO,
  validarEmail,
} from '../utils/convites'
import { CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL, Selo, TD, TH } from '../components/formUi'
import { ConviteLink } from '../components/ConviteLink'

interface EquipePageProps {
  usuario: UsuarioAtual
  onBack: () => void
}

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

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-12 items-start">
          <div className="lg:col-span-6 space-y-1">
            <label htmlFor="eq-email" className={LABEL}>E-mail da pessoa *</label>
            <div className="relative">
              <Mail className="w-4 h-4 text-[#8f8298] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="eq-email"
                type="email"
                className={`${INPUT} pl-9 ${extraEmailClasses(email, emailValido)}`}
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
            <EmailStatusFeedback email={email} valido={emailValido} id="eq-email-feedback" />
          </div>

          <div className="lg:col-span-4 space-y-1">
            <label htmlFor="eq-papel" className={LABEL}>Tipo de acesso</label>
            <div className="relative">
              <User className="w-4 h-4 text-[#8f8298] absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <select
                id="eq-papel"
                className={`${INPUT} pl-9`}
                value={papel}
                onChange={(e) => setPapel(e.target.value as 'admin' | 'membro')}
              >
                <option value="membro">Membro</option>
                <option value="admin">Administrador</option>
              </select>
            </div>
            <p className="text-[11px] text-[#6e6378] dark:text-[#a093a8]">
              {papel === 'membro'
                ? 'Pode acessar e trabalhar com os documentos da organização.'
                : 'Acesso total à administração e documentos da organização.'}
            </p>
          </div>

          <div className="lg:col-span-2 sm:col-span-2 pt-0 sm:pt-6 flex justify-end">
            <button
              type="submit"
              disabled={saving || !emailValido}
              className="w-full sm:w-auto px-5 py-2.5 rounded-xl text-sm font-bold text-white bg-[#a816be] hover:bg-[#bd19d6] disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer shadow-sm transition-all h-[38px] active:scale-95"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              Criar convite
            </button>
          </div>
        </div>

        <ErroBox message={formError} />

        {/* Card do token/link criado */}
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
            <div className={`${CARD} overflow-hidden`}>
              <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Pessoas com acesso
                  </h3>
                  <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                    Usuários que já podem entrar na organização.
                  </p>
                </div>
                <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300">
                  {usuarios.length} {usuarios.length === 1 ? 'pessoa' : 'pessoas'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Nome</th>
                      <th className={TH}>E-mail</th>
                      <th className={TH}>Nível</th>
                      <th className={TH}>Papel</th>
                      <th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {usuarios.map((u) => (
                      <tr key={u.id} className="hover:bg-purple-50/30 dark:hover:bg-purple-950/10 transition-colors">
                        <td className={TD}>
                          <div className="flex items-center gap-2.5">
                            <div className="w-7 h-7 rounded-lg bg-[#3e1347] dark:bg-[#34163d] text-[#e87bf8] dark:text-[#f38df9] font-bold text-xs flex items-center justify-center shrink-0">
                              {extrairIniciais(u.nome)}
                            </div>
                            <span className="font-bold text-[#2d0a33] dark:text-white truncate">
                              {u.nome}
                            </span>
                          </div>
                        </td>
                        <td className={TD}>{u.email}</td>
                        <td className={TD}>{NIVEL_ROTULO[u.nivel] ?? u.nivel}</td>
                        <td className={TD}>{PAPEL_ROTULO[u.papel] ?? u.papel}</td>
                        <td className={TD}>
                          <Selo tom={u.ativo ? 'verde' : 'cinza'}>
                            {u.ativo ? 'Ativo' : 'Inativo'}
                          </Selo>
                        </td>
                      </tr>
                    ))}
                    {usuarios.length === 0 && (
                      <tr>
                        <td className={TD} colSpan={5}>Nenhum usuário cadastrado.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Tabela de Convites aguardando resposta */}
            <div className={`${CARD} overflow-hidden`}>
              <div className="p-5 border-b border-[#ebe5ef] dark:border-[#2f1e39] flex items-center justify-between gap-2">
                <div>
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Convites aguardando resposta
                  </h3>
                  <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5">
                    Pessoas que ainda não aceitaram o convite.
                  </p>
                </div>
                <span className="inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-100 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300">
                  {convites.length} {convites.length === 1 ? 'convite' : 'convites'}
                </span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>E-mail</th>
                      <th className={TH}>Organização</th>
                      <th className={TH}>Papel</th>
                      <th className={TH}>Situação</th>
                      <th className={TH}>Válido até</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {convites.map((c) => (
                      <tr key={c.id} className="hover:bg-purple-50/30 dark:hover:bg-purple-950/10 transition-colors">
                        <td className={`${TD} font-semibold text-[#2d0a33] dark:text-white`}>
                          {c.email}
                        </td>
                        <td className={TD}>{c.organizacao_nome ?? NIVEL_ROTULO[c.nivel] ?? c.nivel}</td>
                        <td className={TD}>{PAPEL_ROTULO[c.papel] ?? c.papel}</td>
                        <td className={TD}>
                          <Selo tom={c.estado === 'usado' ? 'verde' : c.estado === 'pendente' ? 'ambar' : 'cinza'}>
                            {c.estado === 'pendente' ? 'Aguardando resposta' : ESTADO_CONVITE[c.estado] ?? c.estado}
                          </Selo>
                        </td>
                        <td className={TD}>{formatDataHora(c.expira_em)}</td>
                      </tr>
                    ))}
                    {convites.length === 0 && (
                      <tr>
                        <td className={TD} colSpan={5}>Nenhum convite pendente.</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

export default EquipePage
