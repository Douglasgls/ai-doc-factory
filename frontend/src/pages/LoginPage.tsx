import React, { useState } from 'react'
import { AlertCircle, Check, Eye, EyeOff, Loader2, Lock, LogIn, ShieldCheck, User } from 'lucide-react'
import { login } from '../services/api'
import { EviDocsBrand } from '../components/EviDocsBrand'

interface LoginPageProps {
  onSuccess: () => void
}

const LoginPage: React.FC<LoginPageProps> = ({ onSuccess }) => {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [manterConectado, setManterConectado] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [showEsqueciAviso, setShowEsqueciAviso] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isLoading) return
    if (!usuario.trim() || !senha) {
      setError('Preencha seu usuário e senha para continuar.')
      return
    }
    setError(null)
    setIsLoading(true)
    try {
      await login(usuario, senha)
      onSuccess()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao entrar.')
      setIsLoading(false)
    }
  }

  return (
    <div className="min-h-[80vh] flex items-center justify-center p-2 sm:p-4 animate-in fade-in duration-300">
      <div className="w-full max-w-[420px] rounded-[24px] p-7 sm:p-8 bg-gradient-to-b from-[#1a0b24]/95 via-[#15081d]/95 to-[#120719]/95 border border-[#321b40] shadow-[0_0_50px_rgba(147,51,234,0.12),0_16px_40px_rgba(0,0,0,0.65)] backdrop-blur-md space-y-6">
        {/* Marca com Animação Tipográfica Direta e Tagline */}
        <div className="flex flex-col items-center justify-center pt-1 text-center">
          <EviDocsBrand sizeClass="text-[34px] sm:text-[38px]" />
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-[#8d7b9d] mt-2.5">
            GESTÃO DOCUMENTAL INTELIGENTE
          </span>
        </div>

        {/* Cabeçalho de Boas-vindas com Ícone */}
        <div className="flex items-start gap-3.5 pt-1">
          <div className="w-10 h-10 rounded-xl bg-[#241030] border border-[#3d1d50] flex items-center justify-center text-[#d946ef] shrink-0 mt-0.5 shadow-sm">
            <ShieldCheck className="w-5 h-5 stroke-[2]" />
          </div>
          <div>
            <h1 className="text-lg sm:text-[21px] font-bold text-white tracking-tight leading-snug">
              Vamos começar!
            </h1>
            <p className="text-xs text-[#9c8aa9] mt-0.5 leading-relaxed">
              Entre para acessar os documentos da sua organização.
            </p>
          </div>
        </div>

        {/* Formulário de Autenticação */}
        <form onSubmit={handleSubmit} className="space-y-4" aria-label="Formulário de login" noValidate>
          {/* Campo de Usuário */}
          <div className="space-y-1.5">
            <label htmlFor="usuario" className="block text-xs font-semibold text-[#c4b4d0]">
              Usuário ou e-mail
            </label>
            <div className="relative">
              <User className="w-4 h-4 text-[#7d6a8c] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="usuario"
                type="text"
                autoComplete="username"
                required
                placeholder="Digite seu usuário"
                value={usuario}
                onChange={(e) => {
                  setUsuario(e.target.value)
                  if (error) setError(null)
                }}
                className="w-full pl-10 pr-4 py-3 rounded-xl bg-[#16091f]/90 border border-[#361f46] text-white text-sm placeholder-[#6f5d7e] focus:outline-none focus:border-[#b832d9] focus:ring-1 focus:ring-[#b832d9]/40 transition-all"
              />
            </div>
          </div>

          {/* Campo de Senha */}
          <div className="space-y-1.5">
            <label htmlFor="senha" className="block text-xs font-semibold text-[#c4b4d0]">
              Senha
            </label>
            <div className="relative">
              <Lock className="w-4 h-4 text-[#7d6a8c] absolute left-3.5 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                id="senha"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                placeholder="Digite sua senha"
                value={senha}
                onChange={(e) => {
                  setSenha(e.target.value)
                  if (error) setError(null)
                }}
                className="w-full pl-10 pr-10 py-3 rounded-xl bg-[#16091f]/90 border border-[#361f46] text-white text-sm placeholder-[#6f5d7e] focus:outline-none focus:border-[#b832d9] focus:ring-1 focus:ring-[#b832d9]/40 transition-all"
              />
              <button
                type="button"
                onClick={() => setShowPassword((prev) => !prev)}
                tabIndex={-1}
                aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
                className="absolute right-3.5 top-1/2 -translate-y-1/2 text-[#7d6a8c] hover:text-[#d946ef] transition-colors cursor-pointer p-0.5"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {/* Opções: Manter conectado e Esqueci minha senha */}
          <div className="flex items-center justify-between text-xs pt-1">
            <label className="flex items-center gap-2 cursor-pointer select-none text-[#9d8ba9] hover:text-[#c4b4d0] transition-colors">
              <input
                type="checkbox"
                checked={manterConectado}
                onChange={(e) => setManterConectado(e.target.checked)}
                className="sr-only"
              />
              <span
                className={`w-4 h-4 rounded flex items-center justify-center border transition-all ${manterConectado
                  ? 'bg-[#a816be] border-[#c026d3] text-white'
                  : 'bg-[#16091f] border-[#3d224f] text-transparent'
                  }`}
              >
                <Check className="w-3 h-3 stroke-[3]" />
              </span>
              <span>Manter conectado neste dispositivo</span>
            </label>
            <button
              type="button"
              onClick={() => setShowEsqueciAviso(true)}
              className="text-xs font-medium text-[#d442f5] hover:text-[#e56eff] transition-colors cursor-pointer"
            >
              Esqueci minha senha
            </button>
          </div>

          {/* Mensagem informativa para esqueci minha senha */}
          {showEsqueciAviso && (
            <div className="p-3 rounded-xl bg-purple-950/40 border border-purple-800/50 text-purple-200 text-xs flex items-start justify-between gap-2 animate-in fade-in duration-200">
              <span>Entre em contato com o administrador da sua organização para solicitar a redefinição de acesso.</span>
              <button
                type="button"
                onClick={() => setShowEsqueciAviso(false)}
                className="text-purple-300 hover:text-white font-bold ml-1 cursor-pointer"
              >
                ✕
              </button>
            </div>
          )}

          {/* Mensagem de Erro */}
          {error && (
            <div
              role="alert"
              className="p-3 rounded-xl bg-red-950/30 border border-red-800/60 text-red-300 text-xs flex items-center gap-2 animate-in fade-in duration-200"
            >
              <AlertCircle className="w-4 h-4 shrink-0 text-red-400" />
              <span>{error}</span>
            </div>
          )}

          {/* Botão de Submissão */}
          <button
            type="submit"
            disabled={isLoading}
            className="w-full py-3.5 px-4 rounded-xl font-bold text-sm text-white bg-gradient-to-r from-[#9c14ba] via-[#b417d4] to-[#c41be3] hover:from-[#ad17ce] hover:via-[#c41be6] hover:to-[#d324f2] shadow-[0_4px_22px_rgba(180,23,212,0.35)] disabled:opacity-60 disabled:cursor-not-allowed transition-all cursor-pointer flex items-center justify-center gap-2 active:scale-[0.99] mt-2"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <LogIn className="w-4 h-4 stroke-[2.4]" />
            )}
            <span>{isLoading ? 'Entrando...' : 'Entrar no EviDocs'}</span>
          </button>
        </form>

        {/* Divisor e Rodapé Seguro */}
        <div className="border-t border-[#281535] pt-5 flex items-center justify-center gap-2 text-[11px] text-[#7a6888] select-none">
          <Lock className="w-3.5 h-3.5 shrink-0 text-[#726080]" />
          <span>Seus dados são protegidos durante o acesso.</span>
        </div>
      </div>
    </div>
  )
}

export default LoginPage
