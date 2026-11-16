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

/** Data e hora compactas para tabelas sem scroll (ex: 22/11/26 18:45). */
export function formatDataHoraCurta(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const dia = String(d.getDate()).padStart(2, '0')
  const mes = String(d.getMonth() + 1).padStart(2, '0')
  const ano = String(d.getFullYear()).slice(-2)
  const hora = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${dia}/${mes}/${ano} ${hora}:${min}`
}

/** Formata data e hora por extenso (ex: 22 de novembro de 2026, às 18:12). */
export function formatDataHoraPorExtenso(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  const dia = d.getDate()
  const meses = [
    'janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho',
    'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro',
  ]
  const mes = meses[d.getMonth()]
  const ano = d.getFullYear()
  const hora = String(d.getHours()).padStart(2, '0')
  const min = String(d.getMinutes()).padStart(2, '0')
  return `${dia} de ${mes} de ${ano}, às ${hora}:${min}`
}

/** Iniciais do nome para avatar (ex: "Administrador" -> "AD", "Douglas Paz" -> "DP"). */
export function extrairIniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean)
  if (partes.length === 0) return '?'
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase()
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase()
}

/** Regex de validação estrita de e-mail (requer usuário, domínio e TLD com pelo menos 2 letras). */
export const REGEX_EMAIL = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9]+([.-][a-zA-Z0-9]+)*\.[a-zA-Z]{2,}$/

/** Validação de formato de e-mail (alinhado com o regex e tamanho máximo do backend). */
export function validarEmail(email: string): boolean {
  const v = email.trim()
  if (!v || v.length > 254) return false
  return REGEX_EMAIL.test(v)
}

/** Classes condicionais para destaque de campo de e-mail (verde se válido, vermelho se inválido). */
export function extraEmailClasses(email: string, valido: boolean): string {
  const v = email.trim()
  if (!v) return ''
  return valido
    ? '!border-emerald-500 dark:!border-emerald-500 focus:!ring-emerald-500'
    : '!border-rose-500 dark:!border-rose-500 focus:!ring-rose-500'
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
