/** Identificador técnico do perfil de referência (o usuário só vê "Padrão"). */
export const PERFIL_PADRAO = 'clt_padrao'

export function formatarData(iso: string | null | undefined): string {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}
