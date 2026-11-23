/** Mensagens cruas da API (409 e afins) viram frases completas, com o próximo passo. O contrato da API não muda:
 * quem não reconhece a mensagem recebe o texto original. */
const EXPLICACOES: [RegExp, string][] = [
  [
    /já existe contrato próprio para este CNPJ/i,
    'Esta empresa já está cadastrada. Para reenviar o acesso, gere um novo link em Equipe.',
  ],
  [
    /já existe outro tomador com este nome/i,
    'Já existe outra empresa cadastrada com este nome. Use um nome diferente ou confira se ela já está na lista.',
  ],
  [
    /já existe contrato entre este tomador e este prestador/i,
    'Esta terceirizada já tem contrato com este cliente. Para reenviar o acesso, gere um novo link na lista de contratos.',
  ],
  [
    /terceirizada já cadastrada/i,
    'Esta terceirizada já está cadastrada. Para reenviar o acesso, gere um novo link na lista abaixo.',
  ],
  [
    /este CNPJ já é prestador de contratos não próprios/i,
    'Este CNPJ já está cadastrado como terceirizada e não pode ser usado como empresa própria. Confira o CNPJ.',
  ],
  [
    /^já existe (o tomador|o prestador) .*CNPJ/i,
    'Já existe um cadastro com este CNPJ. Confira a lista antes de cadastrar de novo.',
  ],
  [
    /(organização|terceirizada) desativada/i,
    'Esta empresa está desativada. Reative-a antes de continuar.',
  ],
  [
    /já existe usuário com este e-mail/i,
    'Este e-mail já tem acesso ao sistema. Use outro e-mail.',
  ],
  [
    /já existe convite pendente para este e-mail/i,
    'Já existe um convite pendente para este e-mail. Se ele não aparece na sua lista de convites, peça a quem convidou que gere um novo link.',
  ],
]

export function explicarErro(mensagem: string): string {
  const achada = EXPLICACOES.find(([padrao]) => padrao.test(mensagem))
  return achada ? achada[1] : mensagem
}
