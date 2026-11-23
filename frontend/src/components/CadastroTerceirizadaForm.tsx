import React, { useState } from 'react'
import { Info, Loader2, Plus } from 'lucide-react'
import { apiService, type TerceirizadaCadastrada, type Tomador } from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { extraEmailClasses, validarEmail } from '../utils/convites'
import { CARD, EmailStatusFeedback, ErroBox, INPUT, LABEL } from './formUi'
import { ConviteLink } from './ConviteLink'
import { explicarErro } from '../utils/errosCadastro'

/** Resultado do cadastro, conforme o `acesso` devolvido pela API. */
export const ResultadoTerceirizada: React.FC<{ resultado: TerceirizadaCadastrada }> = ({ resultado }) => (
  <div className="space-y-2 pt-2" data-testid="resultado-terceirizada">
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
  titulo?: string
  subtitulo?: string
  /** Só para a plataforma: clientes para escolher. Sem ela, o cliente é o do login. */
  tomadores?: Tomador[]
  onCadastrada: () => void | Promise<void>
  onTrocarAbaTomadores?: () => void
}

export const CadastroTerceirizadaForm: React.FC<CadastroTerceirizadaFormProps> = ({
  titulo = 'Cadastrar contrato de prestação',
  subtitulo = 'Vincule uma empresa prestadora ao tomador responsável pelo contrato.',
  tomadores,
  onCadastrada,
  onTrocarAbaTomadores,
}) => {
  const [tomadorId, setTomadorId] = useState('')
  const [cnpj, setCnpj] = useState('')
  const [razao, setRazao] = useState('')
  const [email, setEmail] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [resultado, setResultado] = useState<TerceirizadaCadastrada | null>(null)

  const emailValido = validarEmail(email)
  const semTomadores = tomadores !== undefined && tomadores.filter((t) => t.ativo).length === 0

  const cadastrar = async (e: React.FormEvent) => {
    e.preventDefault()
    setFormError(null)
    setResultado(null)
    if (tomadores && !tomadorId) {
      setFormError('Escolha o tomador.')
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
      setFormError(err instanceof Error ? explicarErro(err.message) : 'Erro ao cadastrar terceirizada')
    } finally {
      setSaving(false)
    }
  }

  return (
    <form onSubmit={cadastrar} className={`${CARD} p-6 space-y-5`} aria-label={titulo}>
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1 border-b border-[#ebe5ef] dark:border-[#2f1e39] pb-4">
        <div>
          <span className="text-[11px] font-bold uppercase tracking-wider text-[#d946ef]">
            NOVO CADASTRO
          </span>
          <h3 className="text-base sm:text-lg font-bold text-[#2d0a33] dark:text-white mt-0.5">
            {titulo}
          </h3>
          <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
            {subtitulo}
          </p>
        </div>
        <span className="text-xs text-[#877991] dark:text-[#95849f] self-start sm:self-auto">
          * Campos obrigatórios
        </span>
      </div>

      {semTomadores && (
        <div className="rounded-xl border border-purple-800/40 bg-purple-950/20 p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-start sm:items-center gap-3">
            <div className="w-8 h-8 rounded-full bg-purple-900/40 border border-purple-700/50 flex items-center justify-center text-purple-300 shrink-0 mt-0.5 sm:mt-0">
              <Info className="w-4 h-4" />
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-100 dark:text-white">
                Cadastre um tomador antes de criar o contrato
              </h4>
              <p className="text-xs text-slate-400 dark:text-[#95849f]">
                O contrato precisa estar vinculado à empresa que recebe o serviço.
              </p>
            </div>
          </div>
          {onTrocarAbaTomadores && (
            <button
              type="button"
              onClick={onTrocarAbaTomadores}
              className="px-4 py-2 rounded-xl text-xs font-semibold bg-[#2a1333] hover:bg-[#381a44] text-[#d946ef] border border-[#4a1c59] transition-colors cursor-pointer shrink-0 self-start sm:self-auto"
            >
              Cadastrar tomador
            </button>
          )}
        </div>
      )}

      <div className={`grid gap-4 ${tomadores ? 'sm:grid-cols-2 lg:grid-cols-4' : 'sm:grid-cols-3'}`}>
        {tomadores && (
          <div>
            <label htmlFor="terc-tomador" className={LABEL}>
              Tomador *
            </label>
            <select
              id="terc-tomador"
              className={INPUT}
              value={tomadorId}
              required
              onChange={(e) => setTomadorId(e.target.value)}
            >
              {semTomadores ? (
                <option value="">Nenhum tomador cadastrado</option>
              ) : (
                <>
                  <option value="">Selecione o tomador</option>
                  {tomadores.filter((t) => t.ativo).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.nome}
                    </option>
                  ))}
                </>
              )}
            </select>
          </div>
        )}
        <div>
          <label htmlFor="terc-cnpj" className={LABEL}>
            CNPJ do prestador *
          </label>
          <input
            id="terc-cnpj"
            className={INPUT}
            value={cnpj}
            required
            placeholder="00.000.000/0000-00"
            inputMode="numeric"
            onChange={(e) => setCnpj(maskCnpj(e.target.value))}
          />
        </div>
        <div>
          <label htmlFor="terc-razao" className={LABEL}>
            Razão social do prestador *
          </label>
          <input
            id="terc-razao"
            className={INPUT}
            value={razao}
            required
            placeholder="Ex.: Serviços Horizonte Ltda."
            onChange={(e) => setRazao(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="terc-email" className={LABEL}>
            E-mail do administrador *
          </label>
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
          <span className="block text-[11px] text-[#877991] dark:text-[#95849f] mt-1">
            Usado para enviar o acesso inicial.
          </span>
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
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-[#a816be] hover:bg-[#bd19d6] transition-all cursor-pointer shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
        Cadastrar contrato
      </button>

      {resultado && <ResultadoTerceirizada resultado={resultado} />}
    </form>
  )
}
