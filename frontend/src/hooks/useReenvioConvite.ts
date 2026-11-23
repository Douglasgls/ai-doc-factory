import React, { useState } from 'react'
import { apiService, type Contrato } from '../services/api'
import { validarEmail } from '../utils/convites'
import { explicarErro } from '../utils/errosCadastro'

interface LinkGerado {
  token: string
  expiraEm: string
  titulo: string
  email?: string
  papel?: string
}

/** Estado do "Enviar novo convite" para a terceirizada de um contrato. */
export function useReenvioConvite(aoEnviar: () => void | Promise<void>) {
  const [reenviando, setReenviando] = useState<number | null>(null)
  const [email, setEmail] = useState('')
  const [erro, setErro] = useState<string | null>(null)
  const [enviando, setEnviando] = useState(false)
  const [link, setLink] = useState<LinkGerado | null>(null)
  const [ocupado, setOcupado] = useState<number | null>(null) // prestador com "novo link" ou "revogar" em andamento
  const [erroAcao, setErroAcao] = useState<string | null>(null)
  const [aviso, setAviso] = useState<string | null>(null)

  /** O contrato só diz que há convite em aberto; o id vem da lista de convites (a que a pessoa pode gerenciar). */
  const acharPendente = async (c: Contrato) => {
    const lista = await apiService.getConvites()
    return lista.find((x) => x.estado === 'pendente' && x.nivel === 'prestador' && x.prestador_id === c.prestador_id)
  }

  const executar = async (c: Contrato, acao: (idConvite: number) => Promise<void>) => {
    setErroAcao(null)
    setAviso(null)
    setLink(null)
    setOcupado(c.prestador_id)
    try {
      const pendente = await acharPendente(c)
      if (!pendente) {
        setErroAcao('Não achamos o convite em aberto desta empresa na sua lista. Quem o criou pode gerar um novo link.')
        return
      }
      await acao(pendente.id)
      await aoEnviar()
    } catch (err) {
      setErroAcao(err instanceof Error ? err.message : 'Não foi possível concluir. Tente de novo.')
    } finally {
      setOcupado(null)
    }
  }

  /** Revoga o convite em aberto e cria outro igual, de uma vez: o link antigo para de valer. */
  const gerarNovoLink = (c: Contrato) =>
    executar(c, async (id) => {
      const conv = await apiService.reemitirConvite(id)
      setLink({
        token: conv.token,
        expiraEm: conv.expira_em,
        titulo: c.prestador_razao_social,
        email: conv.email,
        papel: conv.papel,
      })
    })

  const revogar = (c: Contrato) => {
    if (!window.confirm(`Revogar o convite de ${c.prestador_razao_social}? O link já enviado deixa de funcionar.`)) {
      return Promise.resolve()
    }
    return executar(c, async (id) => {
      await apiService.revogarConvite(id)
      setAviso(`Convite de ${c.prestador_razao_social} revogado. O link enviado não funciona mais.`)
    })
  }

  const abrir = (c: Contrato) => {
    setReenviando(c.prestador_id)
    setEmail('')
    setErro(null)
    setLink(null)
    setErroAcao(null)
    setAviso(null)
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
      setLink({
        token: conv.token,
        expiraEm: conv.expira_em,
        titulo: c.prestador_razao_social,
        email: conv.email,
        papel: conv.papel,
      })
      setReenviando(null)
      await aoEnviar()
    } catch (err) {
      setErro(err instanceof Error ? explicarErro(err.message) : 'Erro ao enviar convite')
    } finally {
      setEnviando(false)
    }
  }

  return {
    reenviando, email, setEmail, erro, enviando, link, abrir, enviar, cancelar: () => setReenviando(null),
    ocupado, erroAcao, aviso, gerarNovoLink, revogar,
  }
}

export type ReenvioConvite = ReturnType<typeof useReenvioConvite>
