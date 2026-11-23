import React from 'react'
import { ChevronRight } from 'lucide-react'
import { formatarCnpjVisual } from './conformidadeEmpresa'
import type { Company } from '../types'

interface ConformidadeEmpresasListaProps {
  companies: Company[]
  onSelect: (company: Company) => void
  /** Para o usuário da terceirizada: os tomadores dos contratos de cada empresa (pelo CNPJ, só dígitos). */
  tomadoresPorCnpj?: (cnpj: string) => string[]
}

function classeSituacao(classificacao: Company['classificacao'] | null | undefined): string {
  if (classificacao == null) return 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
  if (classificacao === 'Regular') return 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
  if (classificacao === 'Atenção') return 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
  return 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
}

function classeBarra(score: number): string {
  if (score >= 85) return 'bg-emerald-500'
  if (score >= 65) return 'bg-amber-500'
  return 'bg-red-500'
}

function textoTomadores(nomes: string[]): string {
  if (nomes.length === 0) return ''
  if (nomes.length === 1) return `Contrato com ${nomes[0]}`
  return `Contratos com ${nomes.slice(0, -1).join(', ')} e ${nomes[nomes.length - 1]}`
}

/**
 * Nome da empresa (botão que abre o detalhe da nota) + aviso de nota provisória + tomadores.
 * Serve à tabela (a partir de 640px) e ao cartão do celular.
 */
const Identificacao: React.FC<{
  company: Company
  onSelect: (company: Company) => void
  tomadores: string[]
}> = ({ company, onSelect, tomadores }) => (
  <>
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        onSelect(company)
      }}
      aria-label={`Ver como a nota de ${company.razao_social} foi calculada`}
      className="text-left text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc] hover:underline focus-visible:outline-2 focus-visible:outline-[#9333ea] rounded cursor-pointer break-words"
    >
      {company.razao_social}
    </button>
    {tomadores.length > 0 && (
      <p className="text-xs text-[#6e6378] dark:text-[#a093a8] mt-0.5 break-words">{textoTomadores(tomadores)}</p>
    )}
    <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 mt-0.5">
      {company.provisorio && (
        <span
          title="Esta nota ainda pode mudar: há documentos não analisados ou critérios sem nada para avaliar. Abra os detalhes para ver o motivo."
          className="text-xs text-[#9333ea] dark:text-[#d67bf3] font-medium italic cursor-help"
        >
          Nota provisória
          <span className="sr-only">: esta nota ainda pode mudar; abra os detalhes para ver o motivo.</span>
        </span>
      )}
      <span className="text-xs text-[#6e6378] dark:text-[#a093a8] inline-flex items-center gap-0.5">
        Ver como a nota foi calculada <ChevronRight className="w-3 h-3" aria-hidden="true" />
      </span>
    </div>
  </>
)

const ConformidadeEmpresasLista: React.FC<ConformidadeEmpresasListaProps> = ({
  companies,
  onSelect,
  tomadoresPorCnpj = () => [],
}) => (
  <div className="overflow-hidden rounded-2xl border border-[#ebe5ef] dark:border-[#2f1e39] bg-white dark:bg-[#1a1120] shadow-sm">
    {/* Celular: um cartão por empresa */}
    <ul className="sm:hidden divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
      {companies.map((company) => (
        <li
          key={company.cnpj}
          onClick={() => onSelect(company)}
          className="p-4 space-y-3 cursor-pointer active:bg-[#fdfbfe] dark:active:bg-[#251831]"
        >
          <div className="min-w-0">
            <Identificacao company={company} onSelect={onSelect} tomadores={tomadoresPorCnpj(company.cnpj)} />
          </div>
          <p className="text-xs text-[#6e6378] dark:text-[#a093a8] tabular-nums">
            CNPJ {formatarCnpjVisual(company.cnpj)}
          </p>
          <div className="flex items-center justify-between gap-3">
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${classeSituacao(company.classificacao)}`}
            >
              {company.classificacao ?? 'Sem nota'}
            </span>
            <span className="text-sm text-[#6e6378] dark:text-[#a093a8]">
              Nota{' '}
              <strong className="font-bold text-[#2d0a33] dark:text-[#f8f5fc] tabular-nums">
                {company.score == null ? '—' : `${company.score}%`}
              </strong>
            </span>
          </div>
        </li>
      ))}
    </ul>

    {/* A partir de 640px: tabela */}
    <table className="hidden sm:table w-full text-left border-collapse">
      <thead>
        <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
          <th scope="col" className="px-6 py-4 text-sm font-semibold text-[#6e6378] dark:text-[#a093a8]">Empresa</th>
          <th scope="col" className="px-6 py-4 text-sm font-semibold text-[#6e6378] dark:text-[#a093a8]">CNPJ</th>
          <th scope="col" className="px-6 py-4 text-sm font-semibold text-[#6e6378] dark:text-[#a093a8]">Situação</th>
          <th scope="col" className="px-6 py-4 text-sm font-semibold text-[#6e6378] dark:text-[#a093a8] text-right">Nota</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
        {companies.map((company) => (
          <tr
            key={company.cnpj}
            onClick={() => onSelect(company)}
            className="hover:bg-[#fdfbfe] dark:hover:bg-[#251831] transition-colors cursor-pointer"
          >
            <td className="px-6 py-4">
              <Identificacao company={company} onSelect={onSelect} tomadores={tomadoresPorCnpj(company.cnpj)} />
            </td>
            <td className="px-6 py-4 text-sm text-[#6e6378] dark:text-[#a093a8] tabular-nums">
              {formatarCnpjVisual(company.cnpj)}
            </td>
            <td className="px-6 py-4">
              <span
                className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${classeSituacao(company.classificacao)}`}
              >
                {company.classificacao ?? 'Sem nota'}
              </span>
            </td>
            <td className="px-6 py-4 text-right">
              <div className="flex items-center justify-end gap-2">
                <div className="w-16 h-2 bg-[#f3e8ff] dark:bg-[#2e1065] rounded-full overflow-hidden">
                  <div
                    className={`h-full rounded-full ${classeBarra(company.score)}`}
                    style={{ width: `${company.score}%` }}
                  />
                </div>
                <span className="text-sm font-bold text-[#2d0a33] dark:text-[#f8f5fc] tabular-nums">
                  {company.score == null ? '—' : `${company.score}%`}
                </span>
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)

export default ConformidadeEmpresasLista
