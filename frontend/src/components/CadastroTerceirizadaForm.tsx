import React, { useState } from 'react'
import { Loader2 } from 'lucide-react'
import { apiService, type TerceirizadaCadastrada, type Tomador } from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { extraEmailClasses, validarEmail } from '../utils/convites'
import { BTN, CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL } from './formUi'
import { ConviteLink } from './ConviteLink'

/** Resultado do cadastro, conforme o `acesso` devolvido pela API. */
export const ResultadoTerceirizada: React.FC<{ resultado: TerceirizadaCadastrada }> = ({ resultado }) => (
  <div className="space-y-2" data-testid="resultado-terceirizada">
    <p className="text-sm font-semibold text-[#2d0a33] dark:text-white">
      {resultado.prestador.razao_social} ({formatCnpj(resultado.prestador.cnpj)})
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
        Já existe um convite em aberto para esta terceirizada.
      </p>
    )}
    {resultado.acesso === 'ja_tem_acesso' && (
      <p className="text-sm text-[#6e6378] dark:text-[#a093a8]">
        Esta terceirizada já usa o sistema e passa a ver o contrato com vocês.
      </p>
    )}
  </div>
)

interface CadastroTerceirizadaFormProps {
  titulo: string
  /** Só para a plataforma: clientes para escolher. Sem ela, o cliente é o do login. */
  tomadores?: Tomador[]
  onCadastrada: () => void | Promise<void>
}

export const CadastroTerceirizadaForm: React.FC<CadastroTerceirizadaFormProps> = ({
  titulo,
  tomadores,
  onCadastrada,
}) => {
  const [tomadorId, setTomadorId] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [razao, setRazao] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<TerceirizadaCadastrada | null>(null)

  const emailValido = validarEmail(email)

  const cadastrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResultado(null)
    if (tomadores && !tomadorId) {
      setFormError('Escolha o cliente.')
      return
    }
    if (!isCnpjValido(cnpj)) {
      setFormError('CNPJ inválido: confira os dígitos.')
      return
    }
    if (!validarEmail(email)) {
      setFormError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setSaving(true)
    try {
      const r = await apiService.cadastrarTerceirizada({
        cnpj,
        razao_social: razao.trim(),
        email: email.trim(),
        ...(tomadores ? { tomador_id: Number(tomadorId) } : {}),
      })
      setResultado(r)
      setCnpj('')
      setRazao('')
      setEmail('')
      await onCadastrada()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao cadastrar terceirizada')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={cadastrar} className={`${CARD} p-5 space-y-4`} aria-label={titulo}>
      <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">{titulo}</h3>
      <div className={`grid gap-4 ${tomadores ? 'sm:grid-cols-2 lg:grid-cols-4' : 'sm:grid-cols-3'}`}>
        {tomadores && (
          <div>
            <label htmlFor="terc-tomador" className={LABEL}>Cliente</label>
            <select id="terc-tomador" className={INPUT} value={tomadorId} required
              onChange={(e) => setTomadorId(e.target.value)}>
              <option value="">Selecione</option>
              {tomadores.filter((t) => t.ativo).map((t) => (
                <option key={t.id} value={t.id}>{t.nome}</option>
              ))}
            </select>
          </div>
        )}
        <div>
          <label htmlFor="terc-cnpj" className={LABEL}>CNPJ</label>
          <input id="terc-cnpj" className={INPUT} value={cnpj} required placeholder="00.000.000/0000-00"
            inputMode="numeric" onChange={(e) => setCnpj(maskCnpj(e.target.value))} />
        </div>
        <div>
          <label htmlFor="terc-razao" className={LABEL}>Razão social</label>
          <input id="terc-razao" className={INPUT} value={razao} required
            onChange={(e) => setRazao(e.target.value)} />
        </div>
        <div>
          <label htmlFor="terc-email" className={LABEL}>E-mail do administrador</label>
          <input
            id="terc-email"
            type="email"
            className={`${INPUT} ${extraEmailClasses(email, emailValido)}`}
            value={email}
            required
            aria-invalid={email.trim().length > 0 && !emailValido}
            aria-describedby="terc-email-feedback"
            onChange={(e) => {
              setEmail(e.target.value)
              if (formError) setFormError(null)
            }}
            placeholder="administrador@empresa.com.br"
          />
          <EmailStatusFeedback email={email} valido={emailValido} id="terc-email-feedback" />
        </div>
      </div>
      <ErroBox message={formError} />
      <button
        type="submit"
        disabled={
          saving ||
          (!!tomadores && !tomadorId) ||
          !cnpj ||
          !razao.trim() ||
          !emailValido
        }
        className={BTN}
      >
        {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar terceirizada
      </button>
      {resultado && <ResultadoTerceirizada resultado={resultado} />}
    </form>
  )
}
