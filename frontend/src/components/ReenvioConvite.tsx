import React from 'react'
import { Loader2 } from 'lucide-react'
import { type Contrato } from '../services/api'
import { ESTADO_ACESSO, validarEmail } from '../utils/convites'
import type { ReenvioConvite } from '../hooks/useReenvioConvite'
import { BTN, BTN_SEC, CARD, ErroBox, INPUT, LABEL, Selo, TD } from './formUi'
import { ConviteLink } from './ConviteLink'

export const ConviteGeradoCard: React.FC<{ reenvio: ReenvioConvite }> = ({ reenvio }) =>
  reenvio.link ? (
    <div className={`${CARD} p-5 space-y-3`}>
      <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Convite para {reenvio.link.titulo}</h3>
      <ConviteLink token={reenvio.link.token} expiraEm={reenvio.link.expiraEm} />
    </div>
  ) : null

export const AcessoSelo: React.FC<{ contrato: Contrato }> = ({ contrato }) => (
  <Selo tom={contrato.acesso_prestador === 'ativo' ? 'verde' : contrato.acesso_prestador === 'convite_pendente' ? 'ambar' : 'cinza'}>
    {ESTADO_ACESSO[contrato.acesso_prestador ?? 'sem_acesso']}
  </Selo>
)

export const ReenvioBotao: React.FC<{ contrato: Contrato; reenvio: ReenvioConvite }> = ({ contrato, reenvio }) =>
  contrato.acesso_prestador === 'sem_acesso' && contrato.ativo ? (
    <button type="button" className={BTN_SEC} onClick={() => reenvio.abrir(contrato)}>
      Enviar novo convite
    </button>
  ) : null

/** Linha extra da tabela, com o formulário de e-mail, enquanto o reenvio estiver aberto para este contrato. */
export const ReenvioLinha: React.FC<{ contrato: Contrato; reenvio: ReenvioConvite; colSpan: number }> = ({
  contrato,
  reenvio,
  colSpan,
}) => {
  const [tocado, setTocado] = React.useState(false)
  const emailValido = validarEmail(reenvio.email)
  const mostrarErro = tocado && reenvio.email.trim().length > 0 && !emailValido

  return reenvio.reenviando === contrato.prestador_id ? (
    <tr>
      <td className={TD} colSpan={colSpan}>
        <form onSubmit={(e) => void reenvio.enviar(e, contrato)} className="flex flex-wrap items-end gap-3"
          aria-label="Enviar novo convite">
          <div className="flex-1 min-w-[16rem]">
            <label htmlFor="reenvio-email" className={LABEL}>
              E-mail do administrador ({contrato.prestador_razao_social})
            </label>
            <input
              id="reenvio-email"
              type="email"
              className={`${INPUT} ${mostrarErro ? '!border-rose-400 dark:!border-rose-600 focus:!ring-rose-500' : ''}`}
              value={reenvio.email}
              required
              aria-invalid={mostrarErro ? 'true' : 'false'}
              onChange={(e) => reenvio.setEmail(e.target.value)}
              onBlur={() => setTocado(true)}
              placeholder="administrador@empresa.com.br"
            />
            {mostrarErro && (
              <p className="text-[11px] font-medium text-rose-600 dark:text-rose-400 mt-1">
                Por favor, insira um e-mail válido (ex: usuario@dominio.com).
              </p>
            )}
          </div>
          <button
            type="submit"
            disabled={reenvio.enviando || !reenvio.email.trim() || (tocado && !emailValido)}
            className={BTN}
          >
            {reenvio.enviando && <Loader2 className="w-4 h-4 animate-spin" />}Gerar link
          </button>
          <button
            type="button"
            className={BTN_SEC}
            onClick={() => {
              setTocado(false)
              reenvio.cancelar()
            }}
          >
            Cancelar
          </button>
        </form>
        <div className="mt-3"><ErroBox message={reenvio.erro} /></div>
      </td>
    </tr>
  ) : null
}
