import React, { useState } from 'react'
import { apiService, type Contrato } from '../services/api'
import { validarEmail } from '../utils/convites'

interface LinkGerado {
  token: string
  expiraEm: string
  titulo: string
}

/** Estado do "Enviar novo convite" para a terceirizada de um contrato. */
export function useReenvioConvite(aoEnviar: () => void | Promise<void>) {
  const [reenviando, setReenviando] = useState<number | null>(null)
  const [email, setEmail] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [link, setLink] = useState<LinkGerado | null>(null)

  const abrir = (c: Contrato) => {
    setReenviando(c.prestador_id)
    setEmail('')
    setErro(null)
    setLink(null)
  }

  const enviar = async (e: React.FormEvent, c: Contrato) => {
    e.preventDefault()
    setErro(null)
    if (!validarEmail(email)) {
      setErro('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setEnviando(true)
    try {
      const conv = await apiService.criarConvite({
        email: email.trim(),
        nivel: 'prestador',
        papel: 'admin',
        prestador_id: c.prestador_id,
      })
      setLink({ token: conv.token, expiraEm: conv.expira_em, titulo: c.prestador_razao_social })
      setReenviando(null)
      await aoEnviar()
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Erro ao enviar convite')
    } finally {
      setEnviando(false)
    }
  }

  return { reenviando, email, setEmail, erro, enviando, link, abrir, enviar, cancelar: () => setReenviando(null) }
}

export type ReenvioConvite = ReturnType<typeof useReenvioConvite>
