/** O token vai no FRAGMENTO (depois do #): não chega ao servidor, ao log do nginx nem ao Referer. */
export const CAMINHO_CONVITE = '/convite'

/** Único ponto que monta o link de convite. */
export function montarLinkConvite(token: string): string {
  return `${window.location.origin}${CAMINHO_CONVITE}#${token}`
}

export function estaNaTelaDeConvite(): boolean {
  return window.location.pathname === CAMINHO_CONVITE
}

/** Token do fragmento da URL atual ('' se não houver). */
export function lerTokenDoFragmento(): string {
  return window.location.hash.replace(/^#/, '').trim()
}

/** Data e hora legíveis (pt-BR) de um ISO 8601. */
export function formatDataHora(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

/** Validação de formato de e-mail (alinhado com o regex e tamanho máximo do backend). */
export function validarEmail(email: string): boolean {
  const v = email.trim()
  if (!v || v.length > 254) return false
  return /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)
}

export const ESTADO_CONVITE: Record<string, string> = {
  pendente: 'Pendente',
  usado: 'Usado',
  expirado: 'Expirado',
}

export const ESTADO_ACESSO: Record<string, string> = {
  ativo: 'Com acesso',
  convite_pendente: 'Convite enviado',
  sem_acesso: 'Sem acesso',
}

export const NIVEL_ROTULO: Record<string, string> = {
  plataforma: 'Plataforma',
  tomador: 'Cliente',
  prestador: 'Terceirizada',
}

export const PAPEL_ROTULO: Record<string, string> = { admin: 'Administrador', membro: 'Membro' }
