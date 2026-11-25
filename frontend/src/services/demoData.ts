import type { AnalisePonto } from '../components/auditoriaPonto'
import type { ConformidadeEmpresa } from '../components/conformidadeEmpresa'
import type { Company } from '../types'
import type {
  Contrato,
  ConviteListado,
  DocumentoResponse,
  LoteResumoResponse,
  PerfilJornadaDetalhe,
  Prestador,
  TipoDocumentoResponse,
  Tomador,
  UsuarioAtual,
  UsuarioListado,
} from './api'

/** Mapeamento (lote_id:pagina) -> imagem escaneada real em /demo/*.webp */
export const DEMO_PAGE_IMAGES: Record<string, string> = {
  // Lote 101 — TechBrasil Soluções S.A. (os 7 documentos reais de arquivos_rh)
  '101:1': '/demo/folha_ponto_scan.webp',
  '101:2': '/demo/aso_scan.webp',
  '101:3': '/demo/holerite_scan.webp',
  '101:4': '/demo/atestado_medico_scan.webp',
  '101:5': '/demo/contrato_trabalho_scan.webp',
  '101:6': '/demo/folha_pagamento_scan.webp',
  '101:7': '/demo/recibo_ferias_scan.webp',
  // Lote 102 — Vértice Facilities Ltda.
  '102:1': '/demo/folha_ponto_scan.webp',
  '102:2': '/demo/holerite_scan.webp',
  '102:3': '/demo/aso_scan.webp',
  '102:4': '/demo/recibo_ferias_scan.webp',
  '102:5': '/demo/folha_pagamento_scan.webp',
  // Lote 103 — Atlas Logística Terceirizada S.A.
  '103:1': '/demo/folha_ponto_scan.webp',
  '103:2': '/demo/atestado_medico_scan.webp',
  '103:3': '/demo/contrato_trabalho_scan.webp',
  '103:4': '/demo/holerite_scan.webp',
}

export const DEMO_USUARIO: UsuarioAtual = {
  id: 999,
  email: 'demo@evidocs.com.br',
  nome: 'Visitante Demo',
  nivel: 'plataforma',
  papel: 'admin',
  tomador_id: null,
  prestador_id: null,
}

export const DEMO_TIPOS: TipoDocumentoResponse[] = [
  { slug: 'aso', nome: 'ASO', icone: 'idcard' },
  { slug: 'atestado_medico', nome: 'Atestado Médico', icone: 'file' },
  { slug: 'contrato_trabalho', nome: 'Contrato de Trabalho', icone: 'briefcase' },
  { slug: 'folha_pagamento', nome: 'Folha de Pagamento', icone: 'hash' },
  { slug: 'folha_ponto', nome: 'Folha de Ponto', icone: 'file' },
  { slug: 'holerite', nome: 'Holerite', icone: 'hash' },
  { slug: 'recibo_ferias', nome: 'Recibo de Férias', icone: 'home' },
]

export interface DemoState {
  documentos: DocumentoResponse[]
  revisaoMotivos: Record<number, string>
  analisesPonto: Record<number, AnalisePonto>
  conformidades: Record<string, ConformidadeEmpresa>
  lotes: LoteResumoResponse[]
  tomadores: Tomador[]
  prestadores: Prestador[]
  contratos: Contrato[]
  perfisJornada: PerfilJornadaDetalhe[]
  usuarios: UsuarioListado[]
  convites: ConviteListado[]
  nextDocId: number
  nextLoteId: number
}

const NOW_ISO = new Date().toISOString()
const ONE_HOUR_AGO = new Date(Date.now() - 60 * 60 * 1000).toISOString()
const THREE_HOURS_AGO = new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString()

export function createInitialDemoState(): DemoState {
  const documentos: DocumentoResponse[] = [
    // === LOTE 101: TECHBRASIL SOLUÇÕES S.A. (7 documentos reais de arquivos_rh) ===
    {
      id: 1001,
      lote_id: 101,
      ordem: 1,
      pagina_ini: 1,
      pagina_fim: 1,
      estado: 'classificado',
      tipo: 'folha_ponto',
      confianca: 0.99,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2026-10_folha_ponto_marcos_vinicius_001482.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        competencia: '10/2026',
        matricula: '001482',
        cpf: '***.920.178-**',
        cargo: 'Analista de Suporte Pleno',
      },
      paginas: [
        {
          numero: 1,
          imagem_url: '/lotes/101/paginas/1/imagem',
          texto_ocr:
            'ESPELHO DE PONTO ELETRÔNICO MENSAL (REP-P) - 01/10/2026 A 31/10/2026\nEMPREGADOR: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A. | CNPJ: 42.819.650/0001-88\nCOLABORADOR: 001482 - MARCOS VINÍCIUS OLIVEIRA SANTOS | Horário: Seg a Sex 08:00-12:00 / 13:00-17:48 (44h semanais)\n12/10/2026 FERIADO NACIONAL (Plantão TI) 04:00 HE 100%\n15/10/2026 07:55-12:03 / 13:02-19:48 (10:52h)\n20/10/2026 07:58-12:00 / 13:00-19:48 (10:50h)\n21/10/2026 ABONO ATESTADO MÉDICO (CID J06.9)\n26/10/2026 08:02-12:00 / 13:01-19:49 (10:46h)\nRESUMO: Horas Trabalhadas 184:48h | HE 50%: 10:00h | HE 100%: 04:00h | Banco de Horas: +04:12h',
        },
      ],
    },
    {
      id: 1002,
      lote_id: 101,
      ordem: 2,
      pagina_ini: 2,
      pagina_fim: 2,
      estado: 'em_revisao',
      tipo: 'aso',
      confianca: 0.68,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2026-10_aso_marcos_vinicius_001482.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        data_exame: '01/10/2026',
        tipo_exame: 'Admissional',
        resultado: 'Apto para a função',
        matricula: 'EMP-001482',
        cpf: '***.920.178-**',
      },
      paginas: [
        {
          numero: 2,
          imagem_url: '/lotes/101/paginas/2/imagem',
          texto_ocr:
            'ATESTADO DE SAÚDE OCUPACIONAL - ASO (NR-07)\nCLÍNICA: VIDA & TRABALHO MEDICINA OCUPACIONAL LTDA | Evento eSocial: S-2220 | Data de Emissão: 01/10/2026\nRazão Social: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A. | CNPJ: 42.819.650/0001-88\nNome: MARCOS VINÍCIUS OLIVEIRA SANTOS | Matrícula: EMP-001482\nTIPO DE EXAME: [X] ADMISSIONAL | CONCLUSÃO: [X] APTO PARA A FUNÇÃO',
        },
      ],
    },
    {
      id: 1003,
      lote_id: 101,
      ordem: 3,
      pagina_ini: 3,
      pagina_fim: 3,
      estado: 'classificado',
      tipo: 'holerite',
      confianca: 0.98,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2026-10_holerite_marcos_vinicius_001482.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        competencia: '10/2026',
        matricula: '001482',
        salario_base: 'R$ 5.800,00',
        liquido: 'R$ 2.362,33',
        cpf: '***.920.178-**',
      },
      paginas: [
        {
          numero: 3,
          imagem_url: '/lotes/101/paginas/3/imagem',
          texto_ocr:
            'RECIBO DE PAGAMENTO DE SALÁRIO (HOLERITE) - COMPETÊNCIA 10/2026\nEMPREGADOR: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A. | CNPJ: 42.819.650/0001-88\n0001 SALÁRIO BASE: 5.800,00 | 0014 HE 50% (10:00h): 395,45 | 0018 HE 100% (04:00h): 210,91 | DSR: 116,60\nTOTAL VENCIMENTOS: R$ 6.638,96 | DESCONTOS: R$ 4.276,63 | LÍQUIDO: R$ 2.362,33 | FGTS: R$ 531,12',
        },
      ],
    },
    {
      id: 1004,
      lote_id: 101,
      ordem: 4,
      pagina_ini: 4,
      pagina_fim: 4,
      estado: 'classificado',
      tipo: 'atestado_medico',
      confianca: 0.97,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2026-10_atestado_medico_marcos_vinicius.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        data_atendimento: '21/10/2026',
        afastamento: '1 dia',
        cid: 'J06.9',
        crm: 'CRM/SP 194.821',
        cpf: '***.920.178-**',
      },
      paginas: [
        {
          numero: 4,
          imagem_url: '/lotes/101/paginas/4/imagem',
          texto_ocr:
            'ATESTADO MÉDICO - HOSPITAL E MATERNIDADE SANTA HELENA S/A\nPACIENTE: MARCOS VINÍCIUS OLIVEIRA SANTOS | Data: 21/10/2026 | Afastamento: 01 dia\nCID-10: J06.9 (Infecção aguda das vias aéreas superiores) | Dr. Henrique Moura Cavalcanti - CRM/SP 194.821',
        },
      ],
    },
    {
      id: 1005,
      lote_id: 101,
      ordem: 5,
      pagina_ini: 5,
      pagina_fim: 5,
      estado: 'classificado',
      tipo: 'contrato_trabalho',
      confianca: 0.99,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2024-03_contrato_trabalho_marcos_vinicius.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        data_admissao: '10/03/2024',
        cargo: 'Analista de Suporte Pleno (CBO 3172-10)',
        jornada: '44 horas semanais',
        salario: 'R$ 5.800,00',
        cpf: '***.920.178-**',
      },
      paginas: [
        {
          numero: 5,
          imagem_url: '/lotes/101/paginas/5/imagem',
          texto_ocr:
            'CONTRATO INDIVIDUAL DE TRABALHO POR PRAZO INDETERMINADO (CLT) - CT-2026/1482\nEMPREGADORA: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A., CNPJ 42.819.650/0001-88\nEMPREGADO: MARCOS VINÍCIUS OLIVEIRA SANTOS | Salário: R$ 5.800,00 | Jornada: 44h semanais | Início: 10/03/2024',
        },
      ],
    },
    {
      id: 1006,
      lote_id: 101,
      ordem: 6,
      pagina_ini: 6,
      pagina_fim: 6,
      estado: 'classificado',
      tipo: 'folha_pagamento',
      confianca: 0.98,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'TechBrasil (4 colaboradores ativos)',
      nome_arquivo: '2026-10_folha_pagamento_techbrasil.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        competencia: '10/2026',
        darf_previdenciario: 'R$ 11.396,96',
        fgts_digital: 'R$ 2.496,57',
      },
      paginas: [
        {
          numero: 6,
          imagem_url: '/lotes/101/paginas/6/imagem',
          texto_ocr:
            'FOLHA DE PAGAMENTO ANALÍTICA E RESUMO GERAL - COMPETÊNCIA 10/2026\nEMPRESA: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A. | CNPJ: 42.819.650/0001-88\nTOTAL DARF PREVIDENCIÁRIO (DCTFWeb): R$ 11.396,96 | TOTAL FGTS DIGITAL (8%): R$ 2.496,57',
        },
      ],
    },
    {
      id: 1007,
      lote_id: 101,
      ordem: 7,
      pagina_ini: 7,
      pagina_fim: 7,
      estado: 'classificado',
      tipo: 'recibo_ferias',
      confianca: 0.99,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 1,
      pessoa: 'Marcos Vinícius Oliveira Santos',
      nome_arquivo: '2026-10_recibo_ferias_marcos_vinicius.pdf',
      nome_original: 'lote_techbrasil_10_2026_escaneado.pdf',
      n_paginas: 1,
      processado_em: ONE_HOUR_AGO,
      campos: {
        empresa: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
        cnpj: '42.819.650/0001-88',
        periodo_gozo: '03/11/2026 a 02/12/2026',
        data_pagamento: '29/10/2026',
        liquido: 'R$ 6.225,05',
        cpf: '***.920.178-**',
      },
      paginas: [
        {
          numero: 7,
          imagem_url: '/lotes/101/paginas/7/imagem',
          texto_ocr:
            'DEMONSTRATIVO E RECIBO DE PAGAMENTO DE FÉRIAS (CLT ART. 145)\nEMPREGADOR: TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A. | CNPJ: 42.819.650/0001-88\nPERÍODO DE GOZO: 03/11/2026 a 02/12/2026 | LÍQUIDO PAGO: R$ 6.225,05 em 29/10/2026',
        },
      ],
    },

    // === LOTE 102: VÉRTICE FACILITIES LTDA. (Regular · 94/100) ===
    {
      id: 1008,
      lote_id: 102,
      ordem: 1,
      pagina_ini: 1,
      pagina_fim: 1,
      estado: 'classificado',
      tipo: 'folha_ponto',
      confianca: 0.99,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 2,
      pessoa: 'Patrícia Almeida Nogueira',
      nome_arquivo: '2026-10_folha_ponto_vertice_000419.pdf',
      nome_original: 'lote_vertice_facilities_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'VÉRTICE FACILITIES LTDA.',
        cnpj: '31.402.890/0001-12',
        competencia: '10/2026',
        matricula: '000419',
        escala: '12x36 (CCT Facilities SP)',
        cpf: '***.412.880-**',
      },
      paginas: [
        {
          numero: 1,
          imagem_url: '/lotes/102/paginas/1/imagem',
          texto_ocr:
            'ESPELHO DE PONTO (REP-P) - 10/2026 | VÉRTICE FACILITIES LTDA. | CNPJ: 31.402.890/0001-12\nCOLABORADOR: PATRÍCIA ALMEIDA NOGUEIRA | ESCALA 12x36 | 15 plantões regulares | 0h extras excedentes.',
        },
      ],
    },
    {
      id: 1009,
      lote_id: 102,
      ordem: 2,
      pagina_ini: 2,
      pagina_fim: 2,
      estado: 'classificado',
      tipo: 'holerite',
      confianca: 0.98,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 2,
      pessoa: 'Patrícia Almeida Nogueira',
      nome_arquivo: '2026-10_holerite_vertice_000419.pdf',
      nome_original: 'lote_vertice_facilities_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'VÉRTICE FACILITIES LTDA.',
        cnpj: '31.402.890/0001-12',
        competencia: '10/2026',
        salario_base: 'R$ 2.480,00',
        fgts: 'R$ 222,69',
        cpf: '***.412.880-**',
      },
      paginas: [
        {
          numero: 2,
          imagem_url: '/lotes/102/paginas/2/imagem',
          texto_ocr: 'HOLERITE 10/2026 | VÉRTICE FACILITIES LTDA. | CNPJ: 31.402.890/0001-12 | Salário Base R$ 2.480,00',
        },
      ],
    },
    {
      id: 1010,
      lote_id: 102,
      ordem: 3,
      pagina_ini: 3,
      pagina_fim: 3,
      estado: 'classificado',
      tipo: 'aso',
      confianca: 0.97,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 2,
      pessoa: 'Patrícia Almeida Nogueira',
      nome_arquivo: '2026-09_aso_vertice_000419.pdf',
      nome_original: 'lote_vertice_facilities_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'VÉRTICE FACILITIES LTDA.',
        cnpj: '31.402.890/0001-12',
        data_exame: '14/09/2026',
        tipo_exame: 'Periódico',
        resultado: 'Apto',
      },
      paginas: [
        {
          numero: 3,
          imagem_url: '/lotes/102/paginas/3/imagem',
          texto_ocr: 'ASO PERIÓDICO (NR-07) | VÉRTICE FACILITIES LTDA. | CNPJ: 31.402.890/0001-12 | APTO',
        },
      ],
    },
    {
      id: 1011,
      lote_id: 102,
      ordem: 4,
      pagina_ini: 4,
      pagina_fim: 4,
      estado: 'classificado',
      tipo: 'recibo_ferias',
      confianca: 0.98,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 2,
      pessoa: 'Patrícia Almeida Nogueira',
      nome_arquivo: '2026-10_recibo_ferias_vertice.pdf',
      nome_original: 'lote_vertice_facilities_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'VÉRTICE FACILITIES LTDA.',
        cnpj: '31.402.890/0001-12',
        data_pagamento: '28/10/2026',
        liquido: 'R$ 3.110,40',
      },
      paginas: [
        {
          numero: 4,
          imagem_url: '/lotes/102/paginas/4/imagem',
          texto_ocr: 'RECIBO DE FÉRIAS | VÉRTICE FACILITIES LTDA. | Pago dentro do prazo do Art. 145 CLT.',
        },
      ],
    },
    {
      id: 1012,
      lote_id: 102,
      ordem: 5,
      pagina_ini: 5,
      pagina_fim: 5,
      estado: 'classificado',
      tipo: 'folha_pagamento',
      confianca: 0.96,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 2,
      pessoa: 'Vértice Facilities (18 ativos)',
      nome_arquivo: '2026-10_folha_pagamento_vertice.pdf',
      nome_original: 'lote_vertice_facilities_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'VÉRTICE FACILITIES LTDA.',
        cnpj: '31.402.890/0001-12',
        competencia: '10/2026',
      },
      paginas: [
        {
          numero: 5,
          imagem_url: '/lotes/102/paginas/5/imagem',
          texto_ocr: 'FOLHA DE PAGAMENTO 10/2026 | VÉRTICE FACILITIES LTDA. | 18 colaboradores ativos.',
        },
      ],
    },

    // === LOTE 103: ATLAS LOGÍSTICA TERCEIRIZADA S.A. (Crítico · 52/100) ===
    {
      id: 1013,
      lote_id: 103,
      ordem: 1,
      pagina_ini: 1,
      pagina_fim: 1,
      estado: 'classificado',
      tipo: 'folha_ponto',
      confianca: 0.96,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 3,
      pessoa: 'Carlos Henrique Barbosa',
      nome_arquivo: '2026-10_folha_ponto_atlas_002910.pdf',
      nome_original: 'lote_atlas_logistica_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
        cnpj: '58.910.224/0001-67',
        competencia: '10/2026',
        matricula: '002910',
        cpf: '***.801.329-**',
      },
      paginas: [
        {
          numero: 1,
          imagem_url: '/lotes/103/paginas/1/imagem',
          texto_ocr:
            'ESPELHO DE PONTO 10/2026 | ATLAS LOGÍSTICA TERCEIRIZADA S.A. | CNPJ: 58.910.224/0001-67\nCARLOS HENRIQUE BARBOSA | 231:20h trabalhadas | 38:40h HE 50% | 11 dias > 10h | 8 dias consecutivos sem DSR.',
        },
      ],
    },
    {
      id: 1014,
      lote_id: 103,
      ordem: 2,
      pagina_ini: 2,
      pagina_fim: 2,
      estado: 'em_revisao',
      tipo: 'atestado_medico',
      confianca: 0.54,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 3,
      pessoa: 'Carlos Henrique Barbosa',
      nome_arquivo: '2026-10_pagina_borrada_atlas.pdf',
      nome_original: 'lote_atlas_logistica_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
        cnpj: '58.910.224/0001-67',
        data_atendimento: '18/10/2026',
        crm: 'Ilegível no scan',
      },
      paginas: [
        {
          numero: 2,
          imagem_url: '/lotes/103/paginas/2/imagem',
          texto_ocr: 'ATESTADO MÉDICO [CARIMBO BORRADO] | DATA: 18/10/2026 | CRM: [ILEGÍVEL]',
        },
      ],
    },
    {
      id: 1015,
      lote_id: 103,
      ordem: 3,
      pagina_ini: 3,
      pagina_fim: 3,
      estado: 'em_revisao',
      tipo: 'contrato_trabalho',
      confianca: 0.63,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 3,
      pessoa: 'Carlos Henrique Barbosa',
      nome_arquivo: '2026-10_contrato_sem_assinatura_atlas.pdf',
      nome_original: 'lote_atlas_logistica_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
        cnpj: '58.910.224/0001-67',
        jornada: '44 horas semanais',
        assinatura: 'Não detectada',
      },
      paginas: [
        {
          numero: 3,
          imagem_url: '/lotes/103/paginas/3/imagem',
          texto_ocr: 'CONTRATO DE TRABALHO (CLT) | ATLAS LOGÍSTICA | Assinatura do empregado em branco.',
        },
      ],
    },
    {
      id: 1016,
      lote_id: 103,
      ordem: 4,
      pagina_ini: 4,
      pagina_fim: 4,
      estado: 'classificado',
      tipo: 'holerite',
      confianca: 0.97,
      modelo: 'jev-classificador-v3',
      versao_prompt: 'v4',
      contrato_id: 3,
      pessoa: 'Carlos Henrique Barbosa',
      nome_arquivo: '2026-10_holerite_atlas_002910.pdf',
      nome_original: 'lote_atlas_logistica_10_2026.pdf',
      n_paginas: 1,
      processado_em: THREE_HOURS_AGO,
      campos: {
        empresa: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
        cnpj: '58.910.224/0001-67',
        competencia: '10/2026',
        he_50_pagas: '20:00h (divergente do ponto)',
      },
      paginas: [
        {
          numero: 4,
          imagem_url: '/lotes/103/paginas/4/imagem',
          texto_ocr: 'HOLERITE 10/2026 | ATLAS LOGÍSTICA | HE 50% pagas: 20:00h (ponto aponta 38:40h).',
        },
      ],
    },
  ]

  const revisaoMotivos: Record<number, string> = {
    1002: 'baixa_confianca',
    1014: 'qualidade_baixa',
    1015: 'baixa_confianca',
  }

  const perfilPadraoEfetivo = {
    jornada_diaria_min: { valor: 480, base_legal: 'Art. 7º, XIII CF/88 e Art. 58 da CLT' },
    jornada_semanal_min: {
      valor: 2640,
      base_legal: 'Art. 7º, XIII CF/88',
      vigencias: [
        { desde: '2026-12-16', valor: 2520, base_legal: 'EC 141/2026 (42h semanais)' },
        { desde: '2027-12-16', valor: 2400, base_legal: 'EC 141/2026 (40h semanais)' },
      ],
    },
    tolerancia_marcacao_min: { valor: 5, base_legal: 'Art. 58, §1º da CLT' },
    tolerancia_dia_min: { valor: 10, base_legal: 'Art. 58, §1º da CLT' },
    extras_max_dia_min: { valor: 120, base_legal: 'Art. 59 da CLT' },
    adicional_extra_pct: { valor: 50, base_legal: 'Art. 7º, XVI CF/88' },
    intervalo_longo_acima_min: { valor: 360, base_legal: 'Art. 71 da CLT' },
    intervalo_longo_min: { valor: 60, base_legal: 'Art. 71 da CLT' },
    intervalo_curto_acima_min: { valor: 240, base_legal: 'Art. 71, §1º da CLT' },
    intervalo_curto_min: { valor: 15, base_legal: 'Art. 71, §1º da CLT' },
    interjornada_min: { valor: 660, base_legal: 'Art. 66 da CLT' },
    descanso_semanal_min: { valor: 1440, base_legal: 'Art. 67 da CLT' },
    noturno_inicio_min: { valor: 1320, base_legal: 'Art. 73, §2º da CLT' },
    noturno_fim_min: { valor: 300, base_legal: 'Art. 73, §2º da CLT' },
    hora_noturna_min: { valor: 52.5, base_legal: 'Art. 73, §1º da CLT' },
    adicional_noturno_pct: { valor: 20, base_legal: 'Art. 73 da CLT' },
  }

  const analisesPonto: Record<number, AnalisePonto> = {
    // TechBrasil (dados reais extraídos de arquivos_rh/pdf_texto_selecionavel/folha_ponto_texto.pdf)
    1001: {
      documento_id: 1001,
      estado: 'concluida',
      score_geral: 0.52,
      requer_revisao: false,
      perfil_nome: 'clt_padrao',
      perfil_nome_legivel: 'Padrão CLT + EC 141/2026',
      perfil: perfilPadraoEfetivo,
      ponto_britanico: { conclusivo: true, sinal_risco: false, fracao_uniforme: 0.08, dias: 12 },
      scores_dimensao: {
        horas_extras: { normalizado: 0.68, indeterminada: false },
        intervalos: { normalizado: 0.45, indeterminada: false },
        descanso: { normalizado: 0.05, indeterminada: false },
        registro: { normalizado: 0.1, indeterminada: false },
      },
      marcacoes: [
        { data: '2026-10-01', pares: [['07:58', '12:02'], ['13:01', '17:50']] },
        { data: '2026-10-02', pares: [['08:03', '12:00'], ['12:59', '18:49']] },
        { data: '2026-10-05', pares: [['07:56', '12:01'], ['13:00', '17:49']] },
        { data: '2026-10-06', pares: [['08:01', '12:04'], ['13:03', '19:20']] },
        { data: '2026-10-08', pares: [['08:19', '12:02'], ['13:00', '17:48']] },
        { data: '2026-10-12', pares: [['09:00', '13:00']] },
        { data: '2026-10-13', pares: [['07:57', '12:00'], ['13:01', '19:18']] },
        { data: '2026-10-15', pares: [['07:55', '12:03'], ['13:02', '19:48']] },
        { data: '2026-10-20', pares: [['07:58', '12:00'], ['13:00', '19:48']] },
        { data: '2026-10-26', pares: [['08:02', '12:00'], ['13:01', '19:49']] },
        { data: '2026-10-30', pares: [['07:58', '12:02'], ['13:00', '17:49']] },
      ],
      totais: {
        dias: [
          { data: '2026-10-01', trabalhado_min: 533, extras_min: 0, extras_bruto_min: 5, intervalo_min: 59 },
          { data: '2026-10-02', trabalhado_min: 587, extras_min: 59, extras_bruto_min: 59, intervalo_min: 59 },
          { data: '2026-10-05', trabalhado_min: 534, extras_min: 0, extras_bruto_min: 6, intervalo_min: 59 },
          { data: '2026-10-06', trabalhado_min: 620, extras_min: 92, extras_bruto_min: 92, intervalo_min: 59 },
          { data: '2026-10-08', trabalhado_min: 511, extras_min: 0, extras_bruto_min: 0, intervalo_min: 58 },
          { data: '2026-10-12', trabalhado_min: 240, extras_min: 240, extras_bruto_min: 240, intervalo_min: 0 },
          { data: '2026-10-13', trabalhado_min: 620, extras_min: 92, extras_bruto_min: 92, intervalo_min: 61 },
          { data: '2026-10-15', trabalhado_min: 654, extras_min: 126, extras_bruto_min: 126, intervalo_min: 59 },
          { data: '2026-10-20', trabalhado_min: 650, extras_min: 122, extras_bruto_min: 122, intervalo_min: 60 },
          { data: '2026-10-26', trabalhado_min: 646, extras_min: 118, extras_bruto_min: 118, intervalo_min: 61 },
          { data: '2026-10-30', trabalhado_min: 533, extras_min: 0, extras_bruto_min: 5, intervalo_min: 58 },
        ],
        declarados: { total_horas_min: 11088, horas_extras_min: 840, extras_bruto_min: 840 },
      },
      divergencias: [
        {
          tipo: 'horas_extras_acima_limite',
          data: '2026-10-15',
          minutos: 54,
          base_legal: 'Art. 59 da CLT',
          detalhe: 'Jornada de 10h54 (07:55–12:03 e 13:02–19:48), excedendo o limite de 10h diárias.',
        },
        {
          tipo: 'horas_extras_acima_limite',
          data: '2026-10-20',
          minutos: 50,
          base_legal: 'Art. 59 da CLT',
          detalhe: 'Jornada de 10h50 (07:58–12:00 e 13:00–19:48), excedendo o limite de 10h diárias.',
        },
        {
          tipo: 'horas_extras_acima_limite',
          data: '2026-10-26',
          minutos: 46,
          base_legal: 'Art. 59 da CLT',
          detalhe: 'Jornada de 10h46 (08:02–12:00 e 13:01–19:49), excedendo o limite de 10h diárias.',
        },
        {
          tipo: 'intervalo_intrajornada_insuficiente',
          data: '2026-10-08',
          minutos: 2,
          base_legal: 'Art. 71, §4º da CLT',
          detalhe: 'Intervalo de 58 min (12:02 às 13:00), 2 min abaixo do mínimo legal de 1 hora.',
        },
        {
          tipo: 'intervalo_intrajornada_insuficiente',
          data: '2026-10-30',
          minutos: 2,
          base_legal: 'Art. 71, §4º da CLT',
          detalhe: 'Intervalo de 58 min (12:02 às 13:00), 2 min abaixo do mínimo legal de 1 hora.',
        },
      ],
      analise:
        'Folha de ponto com risco moderado: 3 dias ultrapassaram o limite de 10 horas diárias (Art. 59 CLT) e 2 dias apresentaram intervalo intrajornada de 58 minutos (Art. 71 CLT). O abono do dia 21/10 (CID J06.9) e as horas extras de 12/10 conferem com os demais documentos do lote.',
    },

    // Vértice Facilities (Risco baixo)
    1008: {
      documento_id: 1008,
      estado: 'concluida',
      score_geral: 0.08,
      requer_revisao: false,
      perfil_nome: 'cct_facilities_12x36',
      perfil_nome_legivel: 'CCT Facilities SP · 12×36',
      perfil: {
        ...perfilPadraoEfetivo,
        jornada_diaria_min: { valor: 720, base_legal: 'Art. 59-A da CLT + CCT SEAC-SP' },
        adicional_extra_pct: { valor: 60, base_legal: 'CCT SEAC-SP 2026/2027' },
      },
      ponto_britanico: { conclusivo: true, sinal_risco: false, fracao_uniforme: 0.05, dias: 15 },
      scores_dimensao: {
        horas_extras: { normalizado: 0.0, indeterminada: false },
        intervalos: { normalizado: 0.05, indeterminada: false },
        descanso: { normalizado: 0.0, indeterminada: false },
        registro: { normalizado: 0.1, indeterminada: false },
      },
      marcacoes: [
        { data: '2026-10-01', pares: [['07:02', '12:00'], ['13:02', '19:01']] },
        { data: '2026-10-03', pares: [['06:58', '12:03'], ['13:05', '18:59']] },
        { data: '2026-10-05', pares: [['07:01', '12:01'], ['13:02', '19:03']] },
      ],
      totais: {
        dias: [
          { data: '2026-10-01', trabalhado_min: 657, extras_min: 0, extras_bruto_min: 0, intervalo_min: 62 },
          { data: '2026-10-03', trabalhado_min: 659, extras_min: 0, extras_bruto_min: 0, intervalo_min: 62 },
          { data: '2026-10-05', trabalhado_min: 661, extras_min: 0, extras_bruto_min: 0, intervalo_min: 61 },
        ],
        declarados: { total_horas_min: 10800, horas_extras_min: 0 },
      },
      divergencias: [],
      analise: 'Escala 12×36 regular perante a CCT Facilities SP, sem horas extras habituais e com intervalos integrais.',
    },

    // Atlas Logística (Risco alto)
    1013: {
      documento_id: 1013,
      estado: 'concluida',
      score_geral: 0.89,
      requer_revisao: true,
      perfil_nome: 'clt_padrao',
      perfil_nome_legivel: 'Padrão CLT + EC 141/2026',
      perfil: perfilPadraoEfetivo,
      ponto_britanico: { conclusivo: true, sinal_risco: true, fracao_uniforme: 0.72, dias: 22 },
      scores_dimensao: {
        horas_extras: { normalizado: 0.95, indeterminada: false },
        intervalos: { normalizado: 0.88, indeterminada: false },
        descanso: { normalizado: 0.9, indeterminada: false },
        registro: { normalizado: 0.75, indeterminada: false },
      },
      marcacoes: [
        { data: '2026-10-05', pares: [['07:00', '12:00'], ['12:35', '19:45']] },
        { data: '2026-10-06', pares: [['07:00', '12:00'], ['12:35', '20:10']] },
        { data: '2026-10-07', pares: [['07:00', '12:00'], ['12:35', '19:50']] },
        { data: '2026-10-08', pares: [['07:00', '12:00'], ['12:35', '19:30']] },
      ],
      totais: {
        dias: [
          { data: '2026-10-05', trabalhado_min: 730, extras_min: 202, extras_bruto_min: 202, intervalo_min: 35 },
          { data: '2026-10-06', trabalhado_min: 755, extras_min: 227, extras_bruto_min: 227, intervalo_min: 35 },
          { data: '2026-10-07', trabalhado_min: 735, extras_min: 207, extras_bruto_min: 207, intervalo_min: 35 },
          { data: '2026-10-08', trabalhado_min: 715, extras_min: 187, extras_bruto_min: 187, intervalo_min: 35 },
        ],
        declarados: { total_horas_min: 13880, horas_extras_min: 1200, extras_bruto_min: 2320 },
      },
      divergencias: [
        {
          tipo: 'horas_extras_acima_limite',
          data: '2026-10-06',
          minutos: 155,
          base_legal: 'Art. 59 da CLT',
          detalhe: 'Jornada de 12h35 no turno, ultrapassando em 2h35 o teto diário de 10 horas.',
        },
        {
          tipo: 'intervalo_intrajornada_insuficiente',
          data: '2026-10-05',
          minutos: 25,
          base_legal: 'Art. 71, §4º da CLT',
          detalhe: 'Intervalo de 35 min (12:00 às 12:35) em jornada superior a 6h.',
        },
        {
          tipo: 'descanso_semanal_ausente',
          data: '2026-10-12',
          minutos: null,
          base_legal: 'Art. 67 da CLT + OJ 410 TST',
          detalhe: '8 dias consecutivos trabalhados entre 05/10 e 12/10 sem folga compensatória.',
        },
        {
          tipo: 'total_declarado_divergente',
          data: null,
          minutos: 1120,
          campo: 'horas_extras',
          base_legal: 'Art. 59, §1º da CLT',
          detalhe: 'Espelho aponta 38h40 de HE 50%, mas holerite quitou apenas 20h00.',
        },
      ],
      analise:
        'Risco crítico de passivo trabalhista subsidiário: horas extras habituais acima de 10h/dia, supressão recorrente de intervalo intrajornada, ausência de DSR e divergência de 18h40 não pagas no holerite.',
    },
  }

  const conformidades: Record<string, ConformidadeEmpresa> = {
    '42.819.650/0001-88': {
      cnpj: '42.819.650/0001-88',
      razao_social: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
      documentos_por_tipo: {
        aso: 1,
        atestado_medico: 1,
        contrato_trabalho: 1,
        folha_pagamento: 1,
        folha_ponto: 1,
        holerite: 1,
        recibo_ferias: 1,
      },
      data_referencia: '2026-11-25',
      geral: {
        score: 78,
        score_bruto: 78,
        classificacao: 'Atenção',
        provisorio: true,
        criterios: {
          completude: { peso: 40, peso_efetivo: 40, nota: 1, pendente: false, aplicavel: true, bons: 7, ruins: 0 },
          validade: { peso: 35, peso_efetivo: 35, nota: 0.72, pendente: false, aplicavel: true, bons: 1, ruins: 1 },
          consistencia: { peso: 25, peso_efetivo: 25, nota: 0.68, pendente: false, aplicavel: true, bons: 5, ruins: 1 },
        },
        descontos: [
          {
            criterio: 'consistencia',
            documento: 1002,
            tipo: 'aso',
            regra: 'campo_divergente',
            campo: 'tipo_exame',
            detalhe: 'ASO marcado como Admissional em 01/10/2026, mas contrato indica admissão em 10/03/2024.',
            pontos: 12,
            cpf: '***.920.178-**',
            valores: [
              { documento: 1002, tipo: 'aso', valor: 'Admissional (01/10/2026)' },
              { documento: 1005, tipo: 'contrato_trabalho', valor: 'Admissão em 10/03/2024' },
            ],
          },
          {
            criterio: 'validade',
            documento: 1001,
            tipo: 'folha_ponto',
            regra: 'campo_divergente',
            detalhe: 'Folha de ponto com 3 jornadas acima de 10h (Art. 59 CLT) e 2 intervalos de 58 min (Art. 71 CLT).',
            pontos: 10,
          },
        ],
        pendencias: [
          {
            criterio: 'geral',
            documento: 1002,
            tipo: 'aso',
            motivo: 'Documento aguardando confirmação na fila de revisão humana.',
          },
        ],
      },
      por_tipo: {},
      por_documento: {},
    },
    '31.402.890/0001-12': {
      cnpj: '31.402.890/0001-12',
      razao_social: 'VÉRTICE FACILITIES LTDA.',
      documentos_por_tipo: {
        aso: 1,
        folha_pagamento: 1,
        folha_ponto: 1,
        holerite: 1,
        recibo_ferias: 1,
      },
      data_referencia: '2026-11-25',
      geral: {
        score: 94,
        score_bruto: 94,
        classificacao: 'Regular',
        provisorio: false,
        criterios: {
          completude: { peso: 40, peso_efetivo: 40, nota: 0.9, pendente: false, aplicavel: true, bons: 5, ruins: 0 },
          validade: { peso: 35, peso_efetivo: 35, nota: 1, pendente: false, aplicavel: true, bons: 2, ruins: 0 },
          consistencia: { peso: 25, peso_efetivo: 25, nota: 0.92, pendente: false, aplicavel: true, bons: 5, ruins: 0 },
        },
        descontos: [
          {
            criterio: 'consistencia',
            documento: 1012,
            tipo: 'folha_pagamento',
            regra: 'campo_divergente',
            campo: 'cbo',
            detalhe: 'CBO ausente no resumo de 1 colaborador da folha analítica.',
            pontos: 6,
          },
        ],
        pendencias: [],
      },
      por_tipo: {},
      por_documento: {},
    },
    '58.910.224/0001-67': {
      cnpj: '58.910.224/0001-67',
      razao_social: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
      documentos_por_tipo: {
        atestado_medico: 1,
        contrato_trabalho: 1,
        folha_ponto: 1,
        holerite: 1,
      },
      data_referencia: '2026-11-25',
      geral: {
        score: 52,
        score_bruto: 52,
        classificacao: 'Crítico',
        provisorio: true,
        criterios: {
          completude: { peso: 40, peso_efetivo: 40, nota: 0.57, pendente: false, aplicavel: true, bons: 4, ruins: 3 },
          validade: { peso: 35, peso_efetivo: 35, nota: 0.45, pendente: false, aplicavel: true, bons: 1, ruins: 2 },
          consistencia: { peso: 25, peso_efetivo: 25, nota: 0.52, pendente: false, aplicavel: true, bons: 2, ruins: 2 },
        },
        descontos: [
          {
            criterio: 'completude',
            documento: null,
            tipo: 'aso',
            regra: 'obrigatorio_ausente',
            detalhe: 'ASO periódico vigente não enviado para o contrato ativo.',
            pontos: 18,
          },
          {
            criterio: 'validade',
            documento: 1013,
            tipo: 'folha_ponto',
            regra: 'campo_divergente',
            detalhe: 'Ponto com risco crítico (11 dias > 10h, intervalo de 35 min e 8 dias sem DSR).',
            pontos: 18,
          },
          {
            criterio: 'consistencia',
            documento: 1016,
            tipo: 'holerite',
            regra: 'campo_divergente',
            campo: 'horas_extras',
            detalhe: 'Holerite quitou 20h00 de HE 50% frente a 38h40 apuradas na folha de ponto.',
            pontos: 12,
          },
        ],
        pendencias: [
          {
            criterio: 'geral',
            documento: 1014,
            tipo: 'atestado_medico',
            motivo: 'Digitalização com CRM ilegível aguardando revisão humana.',
          },
          {
            criterio: 'geral',
            documento: 1015,
            tipo: 'contrato_trabalho',
            motivo: 'Assinatura não confirmada no contrato aguardando revisão humana.',
          },
        ],
      },
      por_tipo: {},
      por_documento: {},
    },
  }

  const lotes: LoteResumoResponse[] = [
    {
      id: 101,
      nome_arquivo: 'lote_techbrasil_10_2026_escaneado.pdf',
      estado: 'concluido',
      docs_pendentes: 0,
      contrato_id: 1,
      criado_em: ONE_HOUR_AGO,
      total_documentos: 7,
      em_revisao: 1,
      com_erro: 0,
    },
    {
      id: 102,
      nome_arquivo: 'lote_vertice_facilities_10_2026.pdf',
      estado: 'concluido',
      docs_pendentes: 0,
      contrato_id: 2,
      criado_em: THREE_HOURS_AGO,
      total_documentos: 5,
      em_revisao: 0,
      com_erro: 0,
    },
    {
      id: 103,
      nome_arquivo: 'lote_atlas_logistica_10_2026.pdf',
      estado: 'concluido',
      docs_pendentes: 0,
      contrato_id: 3,
      criado_em: THREE_HOURS_AGO,
      total_documentos: 4,
      em_revisao: 2,
      com_erro: 0,
    },
  ]

  const tomadores: Tomador[] = [
    {
      id: 1,
      nome: 'Grupo Horizonte Industrial S.A.',
      cnpj: '12.345.678/0001-90',
      ativo: true,
      criado_em: '2026-01-15T10:00:00Z',
    },
  ]

  const prestadores: Prestador[] = [
    {
      id: 1,
      cnpj: '42.819.650/0001-88',
      razao_social: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
      ativo: true,
      criado_em: '2026-02-01T10:00:00Z',
    },
    {
      id: 2,
      cnpj: '31.402.890/0001-12',
      razao_social: 'VÉRTICE FACILITIES LTDA.',
      ativo: true,
      criado_em: '2026-02-10T10:00:00Z',
    },
    {
      id: 3,
      cnpj: '58.910.224/0001-67',
      razao_social: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
      ativo: true,
      criado_em: '2026-03-05T10:00:00Z',
    },
  ]

  const contratos: Contrato[] = [
    {
      id: 1,
      tomador_id: 1,
      prestador_id: 1,
      ativo: true,
      vigencia_inicio: '2026-01-01',
      vigencia_fim: '2027-12-31',
      criado_em: '2026-02-01T10:00:00Z',
      tomador_nome: 'Grupo Horizonte Industrial S.A.',
      tomador_ativo: true,
      prestador_razao_social: 'TECHBRASIL SOLUÇÕES EM TECNOLOGIA E LOGÍSTICA S.A.',
      prestador_cnpj: '42.819.650/0001-88',
      prestador_ativo: true,
      acesso_prestador: 'ativo',
      perfil_jornada: 'clt_padrao',
      perfil_jornada_nome: 'Padrão CLT + EC 141/2026',
      perfil_jornada_visivel: true,
      proprio: false,
    },
    {
      id: 2,
      tomador_id: 1,
      prestador_id: 2,
      ativo: true,
      vigencia_inicio: '2025-06-01',
      vigencia_fim: '2027-05-31',
      criado_em: '2026-02-10T10:00:00Z',
      tomador_nome: 'Grupo Horizonte Industrial S.A.',
      tomador_ativo: true,
      prestador_razao_social: 'VÉRTICE FACILITIES LTDA.',
      prestador_cnpj: '31.402.890/0001-12',
      prestador_ativo: true,
      acesso_prestador: 'ativo',
      perfil_jornada: 'cct_facilities_12x36',
      perfil_jornada_nome: 'CCT Facilities SP · 12×36',
      perfil_jornada_visivel: true,
      proprio: false,
    },
    {
      id: 3,
      tomador_id: 1,
      prestador_id: 3,
      ativo: true,
      vigencia_inicio: '2026-03-01',
      vigencia_fim: '2027-02-28',
      criado_em: '2026-03-05T10:00:00Z',
      tomador_nome: 'Grupo Horizonte Industrial S.A.',
      tomador_ativo: true,
      prestador_razao_social: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
      prestador_cnpj: '58.910.224/0001-67',
      prestador_ativo: true,
      acesso_prestador: 'convite_pendente',
      perfil_jornada: 'clt_padrao',
      perfil_jornada_nome: 'Padrão CLT + EC 141/2026',
      perfil_jornada_visivel: true,
      proprio: false,
    },
  ]

  const perfisJornada: PerfilJornadaDetalhe[] = [
    {
      perfil: 'clt_padrao',
      nome: 'Padrão CLT + EC 141/2026',
      sindicato: null,
      vigencia_inicio: null,
      vigencia_fim: null,
      vigente: true,
      geral: true,
      prestador_id: null,
      editavel: false,
      padrao: true,
      proprios: [],
      efetivo: perfilPadraoEfetivo,
    },
    {
      perfil: 'cct_facilities_12x36',
      nome: 'CCT Facilities SP · 12×36',
      sindicato: 'SEAC-SP / SIEMACO-SP',
      vigencia_inicio: '2026-01-01',
      vigencia_fim: '2027-12-31',
      vigente: true,
      geral: true,
      prestador_id: null,
      editavel: true,
      padrao: false,
      proprios: [
        {
          parametro: 'jornada_diaria_min',
          valor: 720,
          unidade: 'min',
          base_legal: 'Art. 59-A da CLT + CCT SEAC-SP',
          vigente_desde: '2026-01-01',
        },
        {
          parametro: 'adicional_extra_pct',
          valor: 60,
          unidade: '%',
          base_legal: 'CCT SEAC-SP 2026/2027',
          vigente_desde: '2026-01-01',
        },
      ],
      efetivo: {
        ...perfilPadraoEfetivo,
        jornada_diaria_min: { valor: 720, base_legal: 'Art. 59-A da CLT + CCT SEAC-SP' },
        adicional_extra_pct: { valor: 60, base_legal: 'CCT SEAC-SP 2026/2027' },
      },
    },
  ]

  const usuarios: UsuarioListado[] = [
    {
      id: 999,
      nome: 'Visitante Demo',
      email: 'demo@evidocs.com.br',
      nivel: 'plataforma',
      papel: 'admin',
      ativo: true,
      criado_em: NOW_ISO,
    },
    {
      id: 1000,
      nome: 'Mariana Costa (Jurídico)',
      email: 'mariana.costa@horizonte.com.br',
      nivel: 'tomador',
      papel: 'admin',
      ativo: true,
      criado_em: '2026-02-01T12:00:00Z',
    },
  ]

  const convites: ConviteListado[] = [
    {
      id: 1,
      email: 'rh@atlaslogistica.com.br',
      nivel: 'prestador',
      papel: 'admin',
      tomador_id: null,
      prestador_id: 3,
      organizacao_nome: 'ATLAS LOGÍSTICA TERCEIRIZADA S.A.',
      estado: 'pendente',
      criado_por: 999,
      criado_em: THREE_HOURS_AGO,
      expira_em: new Date(Date.now() + 6 * 24 * 60 * 60 * 1000).toISOString(),
      usado_em: null,
      usuario_id: null,
    },
  ]

  return {
    documentos,
    revisaoMotivos,
    analisesPonto,
    conformidades,
    lotes,
    tomadores,
    prestadores,
    contratos,
    perfisJornada,
    usuarios,
    convites,
    nextDocId: 2000,
    nextLoteId: 200,
  }
}

export function buildCompaniesSummary(state: DemoState): Company[] {
  return state.prestadores.map((p) => {
    const conf = state.conformidades[p.cnpj]
    const docsDaEmpresa = state.documentos.filter((d) => d.campos?.cnpj === p.cnpj)
    const porTipo: Record<string, number> = {}
    for (const d of docsDaEmpresa) {
      const t = d.tipo || 'desconhecido'
      porTipo[t] = (porTipo[t] || 0) + 1
    }
    const pendentes = docsDaEmpresa.filter((d) => d.estado === 'em_revisao').length
    const score = conf?.geral.score ?? 85
    const classificacao: Company['classificacao'] =
      score >= 85 ? 'Regular' : score >= 65 ? 'Atenção' : 'Crítico'
    return {
      cnpj: p.cnpj,
      razao_social: p.razao_social,
      score,
      classificacao,
      provisorio: pendentes > 0,
      documentos_por_tipo: porTipo,
    }
  })
}

