import React, { useState } from 'react'
import { Check, Copy, Eye, EyeOff, Info, Mail, MessageCircle } from 'lucide-react'
import { formatDataHoraPorExtenso, montarLinkConvite, PAPEL_ROTULO } from '../utils/convites'

interface ConviteLinkProps {
  token: string
  expiraEm: string
  email?: string
  papel?: string
  onClose?: () => void
}

/** Caixa com o link recém-criado. O token só existe agora; não é guardado em lugar nenhum. */
export const ConviteLink: React.FC<ConviteLinkProps> = ({ token, expiraEm, email, papel }) => {
  const [copiado, setCopiado] = useState(false)
  const [revelado, setRevelado] = useState(false)
  const link = montarLinkConvite(token)

  const linkMascarado = `${window.location.host}/convite/••••••••••••••••••••••••`
  const linkExibido = revelado ? link : linkMascarado

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(link)
    } catch {
      // Fallback simples caso clipboard api esteja indisponível
    }
    setCopiado(true)
    setTimeout(() => setCopiado(false), 2000)
  }

  const abrirWhatsApp = () => {
    const texto = `Olá! Aqui está o seu convite de acesso: ${link}`
    window.open(`https://wa.me/?text=${encodeURIComponent(texto)}`, '_blank')
  }

  const abrirEmail = () => {
    const assunto = 'Convite de acesso'
    const corpo = `Olá,\n\nVocê recebeu um convite de acesso.\n\nClique no link abaixo para aceitar seu convite:\n${link}\n\nEste convite é individual e temporário (válido até ${formatDataHoraPorExtenso(expiraEm)}).`
    window.open(`mailto:${email || ''}?subject=${encodeURIComponent(assunto)}&body=${encodeURIComponent(corpo)}`)
  }

  return (
    <div className="rounded-2xl border border-emerald-500/40 bg-gradient-to-br from-[#052818] via-[#062c1b] to-[#031d12] text-white p-5 space-y-4 shadow-lg shadow-emerald-950/30 animate-in fade-in duration-200">
      <div className="flex items-start gap-3.5">
        <div className="w-9 h-9 rounded-full bg-emerald-500/25 border border-emerald-400/50 text-emerald-300 flex items-center justify-center shrink-0 mt-0.5 shadow-sm shadow-emerald-900/50">
          <Check className="w-5 h-5 stroke-[2.5]" />
        </div>
        <div className="flex-1 min-w-0">
          <span className="text-[11px] font-bold tracking-wider text-emerald-300 uppercase">
            CONVITE PRONTO PARA ENVIAR
          </span>
          <h4 className="text-base sm:text-lg font-bold text-white truncate">
            {email || 'Novo convite gerado'}
          </h4>
          <p className="text-xs text-emerald-100/80 mt-0.5">
            Entrará como <span className="font-semibold text-white">{papel ? (PAPEL_ROTULO[papel] ?? papel) : 'Membro'}</span> e poderá aceitar o convite até <span className="font-medium text-white">{formatDataHoraPorExtenso(expiraEm)}</span>.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          onClick={copiar}
          className="px-4 py-2 rounded-xl text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 border border-emerald-400/40 transition-all flex items-center gap-2 cursor-pointer shadow-md shadow-emerald-950/40 active:scale-95"
        >
          {copiado ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
          {copiado ? 'Copiado!' : 'Copiar convite'}
        </button>

        <button
          type="button"
          onClick={abrirWhatsApp}
          className="px-4 py-2 rounded-xl text-xs font-semibold text-emerald-200 bg-[#083a24] hover:bg-[#0c4a2f] border border-emerald-600/50 transition-all flex items-center gap-2 cursor-pointer active:scale-95"
        >
          <MessageCircle className="w-3.5 h-3.5" />
          WhatsApp
        </button>

        <button
          type="button"
          onClick={abrirEmail}
          className="px-4 py-2 rounded-xl text-xs font-semibold text-emerald-200 bg-[#083a24] hover:bg-[#0c4a2f] border border-emerald-600/50 transition-all flex items-center gap-2 cursor-pointer active:scale-95"
        >
          <Mail className="w-3.5 h-3.5" />
          E-mail
        </button>
      </div>

      <div className="flex items-center gap-2 text-[11px] text-emerald-200/80 pt-1">
        <Info className="w-3.5 h-3.5 shrink-0 text-emerald-400" />
        <span>Envie agora. Por segurança, este link é temporário e aparece somente após a criação do convite.</span>
      </div>

      <div className="flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-xl bg-[#031c11] border border-emerald-700/60">
        <div className="font-mono text-xs text-emerald-300/90 truncate select-all">
          {linkExibido}
        </div>
        <button
          type="button"
          onClick={() => setRevelado(!revelado)}
          className="text-xs font-medium text-emerald-300 hover:text-white flex items-center gap-1.5 cursor-pointer shrink-0 transition-colors"
        >
          {revelado ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
          <span>{revelado ? 'Ocultar link' : 'Mostrar link completo'}</span>
        </button>
      </div>
    </div>
  )
}
