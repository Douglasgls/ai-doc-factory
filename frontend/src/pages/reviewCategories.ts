export interface CategoryOption {
  slug: string
  name: string
}

export const OFFICIAL_CATEGORY_OPTIONS: CategoryOption[] = [
  { slug: 'aso', name: 'ASO (Atestado de Saúde Ocupacional)' },
  { slug: 'folha_pagamento', name: 'Folha de pagamento' },
  { slug: 'folha_ponto', name: 'Folha de ponto' },
  { slug: 'holerite', name: 'Holerite' },
  { slug: 'recibo_ferias', name: 'Recibo de férias' },
  { slug: 'atestado_medico', name: 'Atestado médico' },
  { slug: 'contrato_trabalho', name: 'Contrato de trabalho' },
]

/** Categoria inicial da revisão: só o tipo sugerido se for um dos oficiais; senão vazio (o revisor escolhe). */
export function initialReviewCategory(suggestedType: string): string {
  return OFFICIAL_CATEGORY_OPTIONS.some((c) => c.slug === suggestedType)
    ? suggestedType
    : ''
}
