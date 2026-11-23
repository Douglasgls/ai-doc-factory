import React, { useEffect, useState } from 'react'
import { Loader2, UserPlus } from 'lucide-react'
import { aceitarConvite, consultarConvite, ConviteInvalidoError, type ConvitePublico } from '../services/api'
import { lerTokenDoFragmento } from '../utils/convites'
import { rotuloNivel } from '../utils/rotulos'
import { ErroBox, INPUT, LABEL, BTN } from '../components/formUi'

const SENHA_MIN = 8
const MSG_INVALIDO = 'Este convite não é válido, já foi usado ou expirou. Peça um novo a quem te convidou.'

interface AceitarConvitePageProps {
  onSuccess: () => void
}

/** Tela pública (sem login): o token vem do fragmento da URL e nunca é exibido nem registrado. */
const AceitarConvitePage: React.FC<AceitarConvitePageProps> = ({ onSuccess }) => {
  const [token] = useState(lerTokenDoFragmento)
  const [convite, setConvite] = useState<ConvitePublico | null>(null)
  const [estado, setEstado] = useState<'carregando' | 'ok' | 'invalido' | 'falha'>(token ? 'carregando' : 'invalido')
  const [falha, setFalha] = useState<string | null>(null)
  const [nome, setNome] = useState('')
  const [senha, setSenha] = useState('')
  const [confirmar, setConfirmar] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)

  useEffect(() => {
    if (!token) return
    let cancelado = false
    consultarConvite(token)
      .then((c) => {
        if (cancelado) return
        setConvite(c)
        setEstado(c ? 'ok' : 'invalido')
      })
      .catch((err) => {
        if (cancelado) return
        setFalha(err instanceof Error ? err.message : 'Erro ao consultar o convite.')
        setEstado('falha')
      })
    return () => {
      cancelado = true
    }
  }, [token])

  const enviar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (enviando) return
    setErro(null)
    if (senha.length < SENHA_MIN) return setErro(`A senha deve ter ao menos ${SENHA_MIN} caracteres.`)
    if (senha !== confirmar) return setErro('As senhas não conferem.')
    setEnviando(true)
    try {
      await aceitarConvite(token, nome.trim(), senha)
      window.history.replaceState(null, '', '/')
      onSuccess()
    } catch (err) {
      if (err instanceof ConviteInvalidoError) {
        setEstado('invalido')
      } else {
        setErro(err instanceof Error ? err.message : 'Erro ao criar o acesso.')
      }
      setEnviando(false)
    }
  }

  return (
    <div className="min-h-[70vh] flex items-center justify-center animate-in fade-in duration-200">
      <div className="w-full max-w-sm rounded-2xl p-7 border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-xs space-y-5">
        <div className="flex flex-col items-center gap-2">
          <span className="text-xl font-extrabold tracking-tight text-[#3e0b48] dark:text-[#f38df9]">EviDocs</span>
          <h1 className="text-2xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#fdfcfe]">Criar acesso</h1>
        </div>

        {estado === 'carregando' && (
          <div className="flex justify-center py-6">
            <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
          </div>
        )}

        {estado === 'invalido' && (
          <p role="alert" className="text-sm text-center rounded-lg px-3 py-3 bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400">
            {MSG_INVALIDO}
          </p>
        )}

        {estado === 'falha' && <ErroBox message={falha} />}

        {estado === 'ok' && convite && (
          <form onSubmit={enviar} className="space-y-4" aria-label="Criar acesso">
            <p className="text-sm text-center text-[#6f6379] dark:text-[#9f91a6]">
              Você recebeu um convite para{' '}
              <strong className="text-[#2d0a33] dark:text-white">{convite.organizacao_nome ?? (convite.nivel === 'prestador' ? rotuloNivel(convite.nivel, true) : rotuloNivel(convite.nivel))}</strong>.
            </p>
            <div>
              <label htmlFor="conv-email" className={LABEL}>E-mail</label>
              <input id="conv-email" className={INPUT} value={convite.email} readOnly />
            </div>
            <div>
              <label htmlFor="conv-nome" className={LABEL}>Nome</label>
              <input id="conv-nome" className={INPUT} value={nome} required autoFocus autoComplete="name"
                onChange={(e) => setNome(e.target.value)} />
            </div>
            <div>
              <label htmlFor="conv-senha" className={LABEL}>Senha (mínimo {SENHA_MIN} caracteres)</label>
              <input id="conv-senha" type="password" className={INPUT} value={senha} required minLength={SENHA_MIN}
                autoComplete="new-password" onChange={(e) => setSenha(e.target.value)} />
            </div>
            <div>
              <label htmlFor="conv-confirmar" className={LABEL}>Confirmar senha</label>
              <input id="conv-confirmar" type="password" className={INPUT} value={confirmar} required
                autoComplete="new-password" onChange={(e) => setConfirmar(e.target.value)} />
            </div>
            <ErroBox message={erro} />
            <button type="submit" disabled={enviando || !nome.trim() || !senha || !confirmar} className={`${BTN} w-full justify-center`}>
              {enviando ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
              Criar acesso
            </button>
          </form>
        )}
      </div>
    </div>
  )
}

export default AceitarConvitePage
