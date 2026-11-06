import React, { useState } from 'react'
import { Loader2, LogIn, Eye, EyeOff } from 'lucide-react'
import { login } from '../services/api'

interface LoginPageProps {
  onSuccess: () => void
}

const LoginPage: React.FC<LoginPageProps> = ({ onSuccess }) => {
  const [usuario, setUsuario] = useState('')
  const [senha, setSenha] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (isLoading) return
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

  const inputClass =
    'w-full px-4 py-2.5 text-sm rounded-lg bg-[#f8f6fa] dark:bg-[#1d1222] border border-[#e5dfec] dark:border-[#311f3d] text-[#2d0a33] dark:text-[#f5edf9] placeholder-[#8f8298] dark:placeholder-[#776881] focus:outline-none focus:ring-1 focus:ring-[#9333ea] dark:focus:ring-[#c026d3] transition-all'

  return (
    <div className="min-h-[70vh] flex items-center justify-center animate-in fade-in duration-200">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm rounded-2xl p-7 border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-xs space-y-5"
      >
        <div className="flex flex-col items-center gap-2">
          <span className="text-xl font-extrabold tracking-tight text-[#3e0b48] dark:text-[#f38df9]">
            EviDocs
          </span>
          <div className="text-center space-y-1">
            <h1 className="text-2xl font-extrabold tracking-tight text-[#2d0a33] dark:text-[#fdfcfe]">Entrar</h1>
            <p className="text-sm text-[#6f6379] dark:text-[#9f91a6]">Acesse o painel de documentos.</p>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="usuario" className="text-xs font-semibold text-[#6e6378] dark:text-[#a093a8]">
            Usuário
          </label>
          <input
            id="usuario"
            type="text"
            autoComplete="username"
            autoFocus
            required
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            className={inputClass}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="senha" className="text-xs font-semibold text-[#6e6378] dark:text-[#a093a8]">
            Senha
          </label>
          <div className="relative">
            <input
              id="senha"
              type={showPassword ? 'text' : 'password'}
              autoComplete="current-password"
              required
              value={senha}
              onChange={(e) => setSenha(e.target.value)}
              className={`${inputClass} pr-10`}
            />
            <button
              type="button"
              onClick={() => setShowPassword((prev) => !prev)}
              tabIndex={-1}
              aria-label={showPassword ? 'Ocultar senha' : 'Mostrar senha'}
              className="absolute right-3 top-1/2 -translate-y-1/2 p-1 text-[#8f8298] dark:text-[#7f7188] hover:text-[#2d0a33] dark:hover:text-[#f5edf9] transition-colors cursor-pointer"
            >
              {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {error && (
          <p role="alert" className="text-sm rounded-lg px-3 py-2 bg-red-100 dark:bg-red-950/30 text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={isLoading || !usuario || !senha}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-[#3e0b48] hover:bg-[#52105e] dark:bg-[#9917a2] dark:hover:bg-[#b01ebb] shadow-sm disabled:opacity-60 disabled:cursor-not-allowed transition-all cursor-pointer"
        >
          {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
          <span>{isLoading ? 'Entrando...' : 'Entrar'}</span>
        </button>
      </form>
    </div>
  )
}

export default LoginPage
