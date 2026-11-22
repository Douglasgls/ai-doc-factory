import React, { useState } from 'react'
import { Loader2, Plus } from 'lucide-react'
import { apiService, type EmpresaPropriaCadastrada } from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { extraEmailClasses, validarEmail } from '../utils/convites'
import { CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL } from './formUi'
import { ConviteLink } from './ConviteLink'

/** Resultado do cadastro, conforme o `acesso` devolvido pela API. */
const ResultadoEmpresaPropria: React.FC<{ resultado: EmpresaPropriaCadastrada }> = ({ resultado }) => (
  <div className="space-y-2 pt-2" data-testid="resultado-empresa-propria">
    <p className="text-sm font-semibold text-[#2d0a33] dark:text-white">
      {resultado.prestador.nome} ({formatCnpj(resultado.prestador.cnpj)})
    </p>
    {resultado.acesso === 'convite_criado' && resultado.convite && (
      <ConviteLink
        token={resultado.convite.token}
        expiraEm={resultado.convite.expira_em}
        email={resultado.convite.email}
        papel="admin"
      />
    )}
    {resultado.acesso === 'convite_pendente' && (
      <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
        Já existe um convite em aberto para esta empresa.
      </p>
    )}
    {resultado.acesso === 'ja_tem_acesso' && (
      <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
        Esta empresa já usa o sistema e passa a ver o contrato próprio.
      </p>
    )}
  </div>
)

interface CadastroEmpresaPropriaFormProps {
  onCadastrada: () => void | Promise<void>
}

/** Plataforma: cadastra uma empresa com funcionários próprios (sem terceirização) e gera o convite do administrador. */
export const CadastroEmpresaPropriaForm: React.FC<CadastroEmpresaPropriaFormProps> = ({ onCadastrada }) => {
  const [cnpj, setCnpj] = useState('')
  const [razao, setRazao] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<EmpresaPropriaCadastrada | null>(null)

  const emailValido = validarEmail(email)

  const cadastrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResultado(null)
    if (!isCnpjValido(cnpj)) {
      setFormError('CNPJ inválido: confira os dígitos.')
      return
    }
    if (!emailValido) {
      setFormError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setSaving(true)
    try {
      const r = await apiService.cadastrarEmpresaPropria({
        cnpj,
        razao_social: razao.trim(),
        email_admin: email.trim(),
      })
      setResultado(r)
      setCnpj('')
      setRazao('')
      setEmail('')
      await onCadastrada()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao cadastrar empresa própria')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={cadastrar} className={`${CARD} p-6 space-y-5`} aria-label="Empresa própria">
      <div className="border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-4">
        <span className="text-[11px] font-bold uppercase tracking-wider text-[#d946ef]">NOVO CADASTRO</span>
        <h3 className="text-base sm:text-lg font-bold text-[#2d0a33] dark:text-white mt-0.5">Empresa própria</h3>
        <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
          Empresa com funcionários próprios, sem terceirização: o mesmo CNPJ vira tomador e prestador, com um
          contrato próprio entre eles.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label htmlFor="propria-cnpj" className={LABEL}>
            CNPJ da empresa *
          </label>
          <input
            id="propria-cnpj"
            className={INPUT}
            value={cnpj}
            required
            placeholder="00.000.000/0000-00"
            inputMode="numeric"
            onChange={(e) => setCnpj(maskCnpj(e.target.value))}
          />
        </div>
        <div>
          <label htmlFor="propria-razao" className={LABEL}>
            Razão social *
          </label>
          <input
            id="propria-razao"
            className={INPUT}
            value={razao}
            required
            placeholder="Ex.: Padaria Horizonte Ltda."
            onChange={(e) => setRazao(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="propria-email" className={LABEL}>
            E-mail do administrador *
          </label>
          <input
            id="propria-email"
            type="email"
            className={`${INPUT} ${extraEmailClasses(email, emailValido)}`}
            value={email}
            required
            aria-invalid={email.trim().length > 0 && !emailValido}
            aria-describedby="propria-email-feedback"
            onChange={(e) => {
              setEmail(e.target.value)
              if (formError) setFormError(null)
            }}
            placeholder="administrador@empresa.com.br"
          />
          <EmailStatusFeedback email={email} valido={emailValido} id="propria-email-feedback" />
        </div>
      </div>

      <ErroBox message={formError} />

      <button
        type="submit"
        disabled={saving || !cnpj || !razao.trim() || !emailValido}
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#a816be] hover:bg-[#bd19d6] transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        Cadastrar empresa própria
      </button>

      {resultado && <ResultadoEmpresaPropria resultado={resultado} />}
    </form>
  )
}
