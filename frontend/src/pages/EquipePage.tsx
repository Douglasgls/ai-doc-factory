import React, { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  apiService,
  type ConviteCriado,
  type ConviteListado,
  type NovoConvite,
  type UsuarioAtual,
  type UsuarioListado,
} from '../services/api'
import { ESTADO_CONVITE, formatDataHora, NIVEL_ROTULO, PAPEL_ROTULO, validarEmail } from '../utils/convites'
import { BTN, CARD, ErroBox, INPUT, LABEL, Selo, TD, TH } from '../components/formUi'
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
  const [emailTocado, setEmailTocado] = useState(false)
  const [papel, setPapel] = useState<'admin' | 'membro'>('membro')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [criado, setCriado] = useState<ConviteCriado | null>(null)

  const emailValido = validarEmail(email)
  const mostrarErroEmail = emailTocado && email.trim().length > 0 && !emailValido

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
    setEmailTocado(true)
    if (!validarEmail(email)) {
      setFormError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setFormError(null)
    setCriado(null)
    setSaving(true)
    try {
      setCriado(await apiService.criarConvite(conviteParaColega(usuario, email.trim(), papel)))
      setEmail('')
      setEmailTocado(false)
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao criar convite')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button onClick={onBack} className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer">
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Equipe</span>
      </nav>

      <form onSubmit={convidar} className={`${CARD} p-5 space-y-4`} aria-label="Convidar colega">
        <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Convidar colega</h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="eq-email" className={LABEL}>E-mail</label>
            <input
              id="eq-email"
              type="email"
              className={`${INPUT} ${mostrarErroEmail ? '!border-rose-400 dark:!border-rose-600 focus:!ring-rose-500' : ''}`}
              value={email}
              required
              aria-invalid={mostrarErroEmail ? 'true' : 'false'}
              aria-describedby={mostrarErroEmail ? 'eq-email-erro' : undefined}
              onChange={(e) => {
                setEmail(e.target.value)
                if (formError) setFormError(null)
              }}
              onBlur={() => setEmailTocado(true)}
              placeholder="exemplo@empresa.com.br"
            />
            {mostrarErroEmail && (
              <p id="eq-email-erro" className="text-[11px] font-medium text-rose-600 dark:text-rose-400 mt-1">
                Por favor, insira um e-mail válido (ex: usuario@dominio.com).
              </p>
            )}
          </div>
          <div>
            <label htmlFor="eq-papel" className={LABEL}>Papel</label>
            <select id="eq-papel" className={INPUT} value={papel}
              onChange={(e) => setPapel(e.target.value as 'admin' | 'membro')}>
              <option value="membro">Membro</option>
              <option value="admin">Administrador</option>
            </select>
          </div>
        </div>
        <ErroBox message={formError} />
        <button
          type="submit"
          disabled={saving || !email.trim() || (emailTocado && !emailValido)}
          className={BTN}
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}Gerar convite
        </button>
        {criado && <ConviteLink token={criado.token} expiraEm={criado.expira_em} />}
      </form>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />
          <div className={`${CARD} overflow-hidden`}>
            <h3 className="px-5 pt-4 text-sm font-bold text-[#2d0a33] dark:text-white">Usuários ({usuarios.length})</h3>
            <table className="w-full text-left border-collapse mt-3">
              <thead>
                <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <th className={TH}>Nome</th><th className={TH}>E-mail</th>
                  <th className={TH}>Nível</th><th className={TH}>Papel</th><th className={TH}>Situação</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                {usuarios.map((u) => (
                  <tr key={u.id}>
                    <td className={`${TD} font-bold`}>{u.nome}</td>
                    <td className={TD}>{u.email}</td>
                    <td className={TD}>{NIVEL_ROTULO[u.nivel] ?? u.nivel}</td>
                    <td className={TD}>{PAPEL_ROTULO[u.papel] ?? u.papel}</td>
                    <td className={TD}><Selo tom={u.ativo ? 'verde' : 'cinza'}>{u.ativo ? 'Ativo' : 'Inativo'}</Selo></td>
                  </tr>
                ))}
                {usuarios.length === 0 && <tr><td className={TD} colSpan={5}>Nenhum usuário.</td></tr>}
              </tbody>
            </table>
          </div>

          <div className={`${CARD} overflow-hidden`}>
            <h3 className="px-5 pt-4 text-sm font-bold text-[#2d0a33] dark:text-white">Convites ({convites.length})</h3>
            <table className="w-full text-left border-collapse mt-3">
              <thead>
                <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                  <th className={TH}>E-mail</th><th className={TH}>Organização</th><th className={TH}>Papel</th>
                  <th className={TH}>Estado</th><th className={TH}>Válido até</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                {convites.map((c) => (
                  <tr key={c.id}>
                    <td className={`${TD} font-bold`}>{c.email}</td>
                    <td className={TD}>{c.organizacao_nome ?? NIVEL_ROTULO[c.nivel] ?? c.nivel}</td>
                    <td className={TD}>{PAPEL_ROTULO[c.papel] ?? c.papel}</td>
                    <td className={TD}>
                      <Selo tom={c.estado === 'usado' ? 'verde' : c.estado === 'pendente' ? 'ambar' : 'cinza'}>
                        {ESTADO_CONVITE[c.estado] ?? c.estado}
                      </Selo>
                    </td>
                    <td className={TD}>{formatDataHora(c.expira_em)}</td>
                  </tr>
                ))}
                {convites.length === 0 && <tr><td className={TD} colSpan={5}>Nenhum convite.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  )
}

export default EquipePage
