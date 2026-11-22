import type { Contrato, UsuarioAtual } from '../services/api'

type Usuario = Pick<UsuarioAtual, 'nivel'> | null | undefined

/** Plataforma e prestador enviam lotes; o tomador é somente leitura. */
export const podeEnviar = (usuario: Usuario): boolean =>
  usuario?.nivel === 'plataforma' || usuario?.nivel === 'prestador'

/** Revisão, correção de tipo/campos, cancelar, reprocessar e excluir seguem a mesma regra do envio. */
export const podeEditar = (usuario: Usuario): boolean => podeEnviar(usuario)

/** Conformidade por empresa: os três níveis; o backend filtra cada um pelo seu escopo (contratos). */
export const veConformidade = (usuario: Usuario): boolean =>
  usuario?.nivel === 'plataforma' || usuario?.nivel === 'tomador' || usuario?.nivel === 'prestador'

/** Organizações (tomador, prestador, contrato) também é exclusivo da plataforma. */
export const veOrganizacoes = (usuario: Usuario): boolean => usuario?.nivel === 'plataforma'

/** Perfis de jornada (análise de ponto) também são exclusivos da plataforma. */
export const vePerfisJornada = (usuario: Usuario): boolean => usuario?.nivel === 'plataforma'

/** Administradores de qualquer nível convidam colegas e veem a equipe. */
export const podeConvidar = (usuario: Pick<UsuarioAtual, 'papel'> | null | undefined): boolean =>
  usuario?.papel === 'admin'

/** Terceirizadas (cadastro e convite) é a tela do administrador do cliente (tomador). */
export const veTerceirizadas = (usuario: Pick<UsuarioAtual, 'nivel' | 'papel'> | null | undefined): boolean =>
  usuario?.nivel === 'tomador' && usuario?.papel === 'admin'

/** Perfis de jornada em modo SÓ ESCOLHA: o admin de uma empresa própria consulta os perfis e troca o do próprio
 * contrato (criar e editar perfil continuam só da plataforma). */
export const escolhePerfilJornada = (
  usuario: Pick<UsuarioAtual, 'nivel' | 'papel'> | null | undefined,
  contratos: Pick<Contrato, 'proprio'>[]
): boolean => usuario?.papel === 'admin' && ehEmpresaPropria(usuario, contratos)

/** Empresa solo: usuário prestador cujos contratos são TODOS próprios (o mesmo CNPJ é tomador e prestador).
 * Para ele a tela esconde os termos de terceirização (tomador, terceirizada, contrato com o cliente). */
export const ehEmpresaPropria = (
  usuario: Pick<UsuarioAtual, 'nivel'> | null | undefined,
  contratos: Pick<Contrato, 'proprio'>[]
): boolean => usuario?.nivel === 'prestador' && contratos.length > 0 && contratos.every((c) => c.proprio === true)
