/** Mensagens de andamento que a API publica (com siglas e "(s)") viram frases para quem usa o sistema.
 * Mensagem que não for reconhecida passa como veio. */
const paginas = (n: string): string => `${n} ${Number(n) === 1 ? 'página' : 'páginas'}`

const REGRAS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^Lendo OCR de (\d+) página\(s\)\.{3}$/, (m) => `Lendo o texto de ${paginas(m[1])}...`],
  [
    /^OCR de (\d+) página\(s\) concluído · segmentando documentos\.{3}$/,
    (m) => `Texto de ${paginas(m[1])} lido · separando os documentos...`,
  ],
  [/^Iniciando conversão e leitura OCR das páginas\.{3}$/, () => 'Preparando a leitura do texto das páginas...'],
  [/^Falha no processamento de OCR\/segmentação\.$/, () => 'Não foi possível ler o texto e separar os documentos.'],
]

export function humanizarMensagemLote(mensagem: string | null | undefined): string | null {
  if (!mensagem) return null
  for (const [padrao, montar] of REGRAS) {
    const m = mensagem.match(padrao)
    if (m) return montar(m)
  }
  return mensagem
}
