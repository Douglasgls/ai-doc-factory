// Rótulos em português para os códigos que a API devolve (snake_case ou slug).
// Regra: o usuário nunca vê o código cru. Código sem rótulo cai em `rotuloPadrao`.
// As listas de códigos vêm do backend: app/ponto.py, app/conformidade.py, app/extracao.py, app/prompts.py,
// app/roteamento.py e app/config.py. Rótulos em sentence case, escritos do ponto de vista de quem usa.

/** Sufixos técnicos que não fazem sentido para o usuário (`horas_extras_min` -> "Horas extras"). */
const SUFIXOS_TECNICOS = /_(min|pct|h|id)$/

/** Fallback: tira o sufixo técnico, troca `_` por espaço e põe a primeira letra em maiúscula. */
export const rotuloPadrao = (codigo: string | null | undefined): string => {
  const texto = (codigo ?? '').trim().replace(SUFIXOS_TECNICOS, '').replace(/[_\s]+/g, ' ').trim()
  return texto ? texto.charAt(0).toUpperCase() + texto.slice(1) : ''
}

/** Rótulo de `codigo` no mapa `mapa`, ou o fallback. Nunca devolve o código cru. */
export const rotulo = (mapa: Record<string, string>, codigo: string | null | undefined): string =>
  (codigo != null ? mapa[codigo] : undefined) ?? rotuloPadrao(codigo)

/** Para usar no meio de uma frase: primeira letra minúscula, exceto siglas ("CPF", "ASO"). */
export const emFrase = (texto: string): string =>
  /^[A-ZÀ-Ý]{2,}/.test(texto) ? texto : texto.charAt(0).toLowerCase() + texto.slice(1)

// ---------------------------------------------------------------------------------------------
// Análise de ponto (app/ponto.py)
// ---------------------------------------------------------------------------------------------
export const ROTULO_DIVERGENCIA: Record<string, string> = {
  horas_extras_acima_limite: 'Horas extras acima do limite diário',
  semana_acima_limite: 'Semana acima de 44 horas',
  intervalo_intrajornada_insuficiente: 'Intervalo de almoço insuficiente',
  interjornada_insuficiente: 'Intervalo entre jornadas menor que 11h',
  descanso_semanal_ausente: 'Descanso semanal de 24h ausente',
  marcacao_invalida: 'Marcação inválida',
  total_declarado_divergente: 'Total declarado diverge do calculado',
  espelho_incompleto: 'Espelho de ponto incompleto',
}

export const ROTULO_DIMENSAO_PONTO: Record<string, string> = {
  horas_extras: 'Horas extras',
  intervalos: 'Intervalos',
  descanso: 'Descanso',
  registro: 'Registro de ponto',
}

/** Campos que o espelho de ponto eletrônico precisa trazer (Portaria MTP 671/2021, art. 84; CAMPOS_ESPELHO). */
export const ROTULO_CAMPO_ESPELHO: Record<string, string> = {
  empregador_nome: 'Nome do empregador',
  empregador_cnpj_cpf: 'CNPJ ou CPF do empregador',
  trabalhador_nome: 'Nome do trabalhador',
  trabalhador_cpf: 'CPF do trabalhador',
  trabalhador_data_admissao: 'Data de admissão do trabalhador',
  trabalhador_cargo_funcao: 'Cargo ou função do trabalhador',
  data_emissao: 'Data de emissão do relatório',
  periodo: 'Período do relatório',
  horario_jornada_contratual: 'Horário e jornada contratual',
  marcacoes: 'Marcações de ponto',
  duracao_jornadas: 'Duração das jornadas',
}

/** Por que o cálculo do sistema e a leitura da IA diferem (diferencas_gemini[].motivo). */
export const ROTULO_DIFERENCA_IA: Record<string, string> = {
  so_codigo: 'Só o cálculo do sistema encontrou',
  so_gemini: 'Só a leitura da IA encontrou',
  minutos_diferentes: 'Minutos diferentes entre o cálculo e a IA',
}

/** Motivo de uma dimensão do risco não avaliada (scores_dimensao[].motivo). */
export const ROTULO_MOTIVO_NAO_AVALIADA: Record<string, string> = {
  sem_semana_completa: 'A folha não traz semanas completas',
}

// ---------------------------------------------------------------------------------------------
// Campos extraídos dos documentos (app/prompts.py::CAMPOS_EXTRACAO_TEXTO e afins)
// ---------------------------------------------------------------------------------------------
export const ROTULO_CAMPO: Record<string, string> = {
  cnpj_prestadora: 'CNPJ da prestadora',
  razao_social_prestadora: 'Razão social da prestadora',
  distingue_prestadora: 'Distingue prestadora e tomadora',
  nome_empresa: 'Empresa',
  nome: 'Nome',
  cpf: 'CPF',
  rg: 'RG',
  endereco: 'Endereço',
  matricula: 'Matrícula',
  competencia: 'Competência',
  data_admissao: 'Data de admissão',
  data_exame: 'Data do exame',
  data_termino: 'Data de término',
  data_emissao: 'Data de emissão',
  data_vencimento: 'Data de vencimento',
  inicio_ferias: 'Início das férias',
  fim_ferias: 'Fim das férias',
  inicio_periodo: 'Início do período',
  fim_periodo: 'Fim do período',
  tipo_prazo: 'Prazo do contrato',
  tipo_exame: 'Tipo de exame',
}

/** Empresa própria: a dona dos documentos é a própria empresa, sem o termo "prestadora". */
const ROTULO_CAMPO_PROPRIA: Record<string, string> = {
  razao_social_prestadora: 'Razão social da empresa',
  cnpj_prestadora: 'CNPJ da empresa',
}

export const rotuloCampo = (campo: string | null | undefined, propria = false): string =>
  campo ? ((propria ? ROTULO_CAMPO_PROPRIA[campo] : undefined) ?? rotulo({ ...ROTULO_CAMPO, ...ROTULO_CAMPO_ESPELHO }, campo)) : 'Campo'

/** Valores de campos que são códigos (enums de app/prompts.py: TIPOS_PRAZO e TIPOS_EXAME). */
const ROTULO_VALOR_CAMPO: Record<string, Record<string, string>> = {
  tipo_prazo: {
    determinado: 'Prazo determinado',
    indeterminado: 'Prazo indeterminado',
    nao_informado: 'Não informado',
  },
  tipo_exame: {
    admissional: 'Admissional',
    periodico: 'Periódico',
    retorno_trabalho: 'Retorno ao trabalho',
    mudanca_risco: 'Mudança de risco',
    demissional: 'Demissional',
  },
}

/** Valor de um campo para exibir: só os campos de enum são traduzidos; o resto é texto do documento. */
export const rotuloValorCampo = (campo: string, valor: string): string => {
  const mapa = ROTULO_VALOR_CAMPO[campo]
  return mapa ? rotulo(mapa, valor) : valor
}

// ---------------------------------------------------------------------------------------------
// Conformidade (app/conformidade.py)
// ---------------------------------------------------------------------------------------------
export const ROTULO_CRITERIO: Record<string, string> = {
  completude: 'Completude',
  validade: 'Validade',
  consistencia: 'Consistência',
  geral: 'Geral',
}

/** Regras de desconto (descontos[].regra) e de pendência (deduzidas em conformidadeEmpresa.regraDaPendencia). */
export const ROTULO_REGRA: Record<string, string> = {
  obrigatorio_ausente: 'Documento obrigatório não enviado',
  documento_vencido: 'Documento vencido',
  campo_divergente: 'Informação divergente entre documentos',
  cnpj_diferente_do_contrato: 'CNPJ do documento diferente do CNPJ do contrato',
  pendente_revisao: 'Documento aguardando revisão',
  pendente_obrigatorio: 'Obrigatório que pode estar num documento não identificado',
  campo_ausente: 'Campo ausente ou ilegível',
  criterio_sem_dados: 'Critério sem documentos para avaliar',
}

/**
 * O backend manda motivos de pendência e de "sem empresa" como frase com o código entre aspas
 * ("campo 'data_admissao' ausente"). Aqui os códigos viram rótulo; frases sem código passam como vieram.
 * `rotulosTipo` é o mapa de GET /tipos (tipo documental -> nome).
 */
export const rotuloMotivo = (motivo: string, rotulosTipo: Record<string, string> = {}): string => {
  const naoAnalisado = /^documento não analisado \(estado '([^']*)', tipo '([^']*)'\)$/.exec(motivo)
  if (naoAnalisado) {
    const [, estado, tipo] = naoAnalisado
    const situacao = rotulo(ROTULO_ESTADO_DOCUMENTO, estado)
    const nomeTipo = tipo && tipo !== 'desconhecido' && tipo !== 'None' ? (rotulosTipo[tipo] ?? rotuloPadrao(tipo)) : null
    return `Documento ainda não analisado (${emFrase(situacao)}${nomeTipo ? `; tipo sugerido: ${nomeTipo}` : '; tipo não identificado'})`
  }
  const campo = /^campo '([^']*)' (ausente ou ilegível|ausente|inválido)$/.exec(motivo)
  if (campo) return `${rotuloCampo(campo[1])}: ${campo[2] === 'inválido' ? 'valor inválido' : campo[2]}`
  if (motivo === 'obrigatório não encontrado, mas há documento não identificado') {
    return 'Obrigatório não encontrado, mas há documento ainda não identificado'
  }
  if (motivo.startsWith('nada analisável')) return 'Nada para analisar neste critério; o peso passou para os outros'
  return motivo
}

// ---------------------------------------------------------------------------------------------
// Estados e revisão
// ---------------------------------------------------------------------------------------------
export const ROTULO_ESTADO_LOTE: Record<string, string> = {
  recebido: 'Recebido',
  ocr: 'Lendo o texto',
  classificando: 'Classificando',
  concluido: 'Concluído',
  erro: 'Com erro',
}

export const ROTULO_ESTADO_DOCUMENTO: Record<string, string> = {
  segmentado: 'Aguardando classificação',
  classificado: 'Classificado',
  em_revisao: 'Em revisão',
  revisado: 'Revisado',
  erro: 'Com erro',
}

/** Motivo pelo qual o documento foi para a fila de revisão (documento.motivo_revisao; app/roteamento.py). */
export const ROTULO_MOTIVO_REVISAO: Record<string, string> = {
  confianca_baixa: 'Confiança baixa',
  confianca_intermediaria: 'Confiança média',
  desacordo_modelos: 'Os modelos discordaram',
  segmentacao_ambigua: 'Início ou fim incerto',
  nenhum_dos_anteriores: 'Tipo não reconhecido',
}

export const DESCRICAO_MOTIVO_REVISAO: Record<string, string> = {
  confianca_baixa: 'A confiança na classificação ficou muito baixa. Confira o tipo do documento.',
  confianca_intermediaria: 'O sistema sugeriu um tipo, mas sem confiança suficiente para aceitar sozinho. Confirme ou corrija.',
  desacordo_modelos: 'Os dois modelos de IA sugeriram tipos diferentes. Escolha o tipo correto.',
  segmentacao_ambigua: 'Não ficou claro onde este documento começa ou termina. Confira as páginas e o tipo.',
  nenhum_dos_anteriores: 'O documento não parece ser de nenhum dos tipos conhecidos. Escolha o tipo correto.',
}

export const rotuloMotivoRevisao = (motivo: string | null | undefined): string =>
  motivo ? rotulo(ROTULO_MOTIVO_REVISAO, motivo) : 'Revisão pendente'

export const descricaoMotivoRevisao = (motivo: string | null | undefined): string =>
  (motivo ? DESCRICAO_MOTIVO_REVISAO[motivo] : undefined) ?? 'Documento requer verificação manual.'

/** Tipo documental: usa o nome vindo de GET /tipos; `desconhecido` e códigos novos nunca aparecem crus. */
export const rotuloTipoDocumental = (tipo: string | null | undefined, nomes: Record<string, string> = {}): string =>
  !tipo ? 'Documento' : tipo === 'desconhecido' ? 'Tipo não identificado' : (nomes[tipo] ?? rotuloPadrao(tipo))

/** Perfil de jornada padrão do sistema (ponto.PERFIL_PADRAO); perfis criados pelo usuário usam o fallback. */
export const ROTULO_PERFIL_JORNADA: Record<string, string> = { clt_padrao: 'Padrão' }

// ---------------------------------------------------------------------------------------------
// Convites, acesso e equipe (movidos de utils/convites.ts)
// ---------------------------------------------------------------------------------------------
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

/** Rótulo do nível; na empresa própria o prestador é "Empresa" (sem o termo de terceirização). */
export const rotuloNivel = (nivel: string, empresaPropria = false): string =>
  nivel === 'prestador' && empresaPropria ? 'Empresa' : rotulo(NIVEL_ROTULO, nivel)

export const PAPEL_ROTULO: Record<string, string> = { admin: 'Administrador', membro: 'Membro' }
