import type { Contrato } from '../services/api'

/** Mantém só os dígitos e aplica a máscara 00.000.000/0000-00 enquanto digita. */
export function maskCnpj(value: string): string {
  const d = value.replace(/\D/g, '').slice(0, 14)
  let out = d.slice(0, 2)
  if (d.length > 2) out += `.${d.slice(2, 5)}`
  if (d.length > 5) out += `.${d.slice(5, 8)}`
  if (d.length > 8) out += `/${d.slice(8, 12)}`
  if (d.length > 12) out += `-${d.slice(12, 14)}`
  return out
}

/** Formata um CNPJ de 14 dígitos; qualquer outra coisa volta como veio. */
export function formatCnpj(cnpj: string | null | undefined): string {
  if (!cnpj) return ''
  const d = cnpj.replace(/\D/g, '')
  return d.length === 14 ? maskCnpj(d) : cnpj
}

/** Confere os dígitos verificadores no cliente (a API continua sendo a fonte da verdade). */
export function isCnpjValido(cnpj: string): boolean {
  const d = cnpj.replace(/\D/g, '')
  if (d.length !== 14 || /^(\d)\1{13}$/.test(d)) return false
  const dv = (base: string) => {
    const pesos =
      base.length === 12 ? [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2] : [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    const soma = base.split('').reduce((acc, ch, i) => acc + Number(ch) * pesos[i], 0)
    const resto = soma % 11
    return resto < 2 ? 0 : 11 - resto
  }
  const d1 = dv(d.slice(0, 12))
  const d2 = dv(d.slice(0, 12) + d1)
  return d.endsWith(`${d1}${d2}`)
}

/** Rótulo do seletor: "tomador — prestador (CNPJ formatado)". */
export function contratoLabel(
  c: Pick<Contrato, 'tomador_nome' | 'prestador_razao_social' | 'prestador_cnpj'>
): string {
  return `${c.tomador_nome} — ${c.prestador_razao_social} (${formatCnpj(c.prestador_cnpj)})`
}

/** Contrato utilizável em upload: ele, o tomador e o prestador ativos. */
export function contratoUtilizavel(c: Contrato): boolean {
  return c.ativo && c.tomador_ativo && c.prestador_ativo
}

/** Nomes dos tomadores dos contratos (de terceirização, ativos) de uma empresa prestadora, sem repetição. */
export function tomadoresDoPrestador(contratos: Contrato[], cnpj: string): string[] {
  const alvo = cnpj.replace(/\D/g, '')
  const nomes = contratos
    .filter((c) => c.ativo && c.proprio !== true && c.prestador_cnpj.replace(/\D/g, '') === alvo)
    .map((c) => c.tomador_nome)
  return [...new Set(nomes)]
}
