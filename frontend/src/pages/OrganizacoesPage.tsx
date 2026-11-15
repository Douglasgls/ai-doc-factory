import React, { useCallback, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
  apiService,
  type ConviteCriado,
  type Contrato,
  type Prestador,
  type Tomador,
} from '../services/api'
import { formatCnpj, isCnpjValido, maskCnpj } from '../utils/contratos'
import { validarEmail } from '../utils/convites'
import { BTN, BTN_SEC, CARD, ErroBox, INPUT, LABEL, TD, TH } from '../components/formUi'
import { ConviteLink } from '../components/ConviteLink'
import { CadastroTerceirizadaForm } from '../components/CadastroTerceirizadaForm'
import {
  AcessoSelo,
  ConviteGeradoCard,
  ReenvioBotao,
  ReenvioLinha,
} from '../components/ReenvioConvite'
import { useReenvioConvite } from '../hooks/useReenvioConvite'

type Aba = 'tomadores' | 'prestadores' | 'contratos'

const Situacao: React.FC<{ ativo: boolean }> = ({ ativo }) => (
  <span
    className={`inline-flex px-2.5 py-0.5 rounded-full text-xs font-semibold ${
      ativo
        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'
    }`}
  >
    {ativo ? 'Ativo' : 'Inativo'}
  </span>
)

function formatData(iso: string | null): string {
  if (!iso) return '—'
  const [a, m, d] = iso.split('-')
  return `${d}/${m}/${a}`
}

interface OrganizacoesPageProps {
  onBack: () => void
}

const OrganizacoesPage: React.FC<OrganizacoesPageProps> = ({ onBack }) => {
  const [aba, setAba] = useState<Aba>('contratos')
  const [tomadores, setTomadores] = useState<Tomador[]>([])
  const [prestadores, setPrestadores] = useState<Prestador[]>([])
  const [contratos, setContratos] = useState<Contrato[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [formError, setFormError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [tomNome, setTomNome] = useState('')
  const [tomCnpj, setTomCnpj] = useState('')
  const [prestCnpj, setPrestCnpj] = useState('')
  const [prestRazao, setPrestRazao] = useState('')

  // Logo após criar um tomador: convite do primeiro administrador do cliente
  const [tomNovo, setTomNovo] = useState<Tomador | null>(null)
  const [convEmail, setConvEmail] = useState('')
  const [convEmailTocado, setConvEmailTocado] = useState(false)
  const [convSaving, setConvSaving] = useState(false)
  const [convError, setConvError] = useState<string | null>(null)
  const [convCriado, setConvCriado] = useState<ConviteCriado | null>(null)

  const convEmailValido = validarEmail(convEmail)
  const mostrarErroConvEmail = convEmailTocado && convEmail.trim().length > 0 && !convEmailValido

  const carregar = useCallback(async () => {
    try {
      const [t, p, c] = await Promise.all([
        apiService.getTomadores(),
        apiService.getPrestadores(),
        apiService.getContratos(),
      ])
      setTomadores(t)
      setPrestadores(p)
      setContratos(c)
      setLoadError(null)
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Erro ao carregar organizações')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void carregar(), 0)
    return () => clearTimeout(timer)
  }, [carregar])

  const trocarAba = (nova: Aba) => {
    setAba(nova)
    setFormError(null)
  }

  const enviar = async (e: React.FormEvent, acao: () => Promise<void>) => {
    e.preventDefault()
    setFormError(null)
    setSaving(true)
    try {
      await acao()
      await carregar()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  const salvarTomador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (tomCnpj && !isCnpjValido(tomCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      const novo = await apiService.createTomador({ nome: tomNome, cnpj: tomCnpj || null })
      setTomNome('')
      setTomCnpj('')
      setTomNovo(novo)
      setConvEmail('')
      setConvError(null)
      setConvCriado(null)
    })

  const convidarAdminCliente = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!tomNovo) return
    setConvEmailTocado(true)
    if (!validarEmail(convEmail)) {
      setConvError('Por favor, informe um endereço de e-mail válido.')
      return
    }
    setConvError(null)
    setConvSaving(true)
    try {
      setConvCriado(
        await apiService.criarConvite({
          email: convEmail.trim(),
          nivel: 'tomador',
          papel: 'admin',
          tomador_id: tomNovo.id,
        })
      )
      setConvEmail('')
      setConvEmailTocado(false)
    } catch (err) {
      setConvError(err instanceof Error ? err.message : 'Erro ao criar convite')
    } finally {
      setConvSaving(false)
    }
  }

  const salvarPrestador = (e: React.FormEvent) =>
    enviar(e, async () => {
      if (!isCnpjValido(prestCnpj)) throw new Error('CNPJ inválido: confira os dígitos.')
      await apiService.createPrestador({ cnpj: prestCnpj, razao_social: prestRazao })
      setPrestCnpj('')
      setPrestRazao('')
    })

  const reenvio = useReenvioConvite(carregar)

  const abas: { id: Aba; label: string; n: number }[] = [
    { id: 'contratos', label: 'Contratos', n: contratos.length },
    { id: 'tomadores', label: 'Tomadores', n: tomadores.length },
    { id: 'prestadores', label: 'Prestadores', n: prestadores.length },
  ]

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-[#877991] dark:text-[#95849f]">
        <button
          onClick={onBack}
          className="hover:text-[#2d0a33] dark:hover:text-white transition-colors cursor-pointer"
        >
          Documentos
        </button>
        <span>&gt;</span>
        <span className="font-semibold text-[#2d0a33] dark:text-[#f8f5fc]">Organizações</span>
      </nav>

      <div className="flex items-center gap-2">
        {abas.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => trocarAba(a.id)}
            className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all cursor-pointer ${
              aba === a.id
                ? 'bg-[#f4e8f7] text-[#5c1363] dark:bg-[#34163d] dark:text-[#f38df9]'
                : 'text-[#6e6378] dark:text-[#a093a8] hover:text-[#2d0a33] dark:hover:text-white'
            }`}
          >
            {a.label} ({a.n})
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[#9333ea]" />
        </div>
      ) : (
        <>
          <ErroBox message={loadError} />

          {aba === 'tomadores' && (
            <>
              <form onSubmit={salvarTomador} className={`${CARD} p-5 space-y-4`} aria-label="Novo tomador">
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Novo tomador</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="tom-nome" className={LABEL}>Nome</label>
                    <input id="tom-nome" className={INPUT} value={tomNome} required
                      onChange={(e) => setTomNome(e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="tom-cnpj" className={LABEL}>CNPJ (opcional)</label>
                    <input id="tom-cnpj" className={INPUT} value={tomCnpj} placeholder="00.000.000/0000-00"
                      inputMode="numeric" onChange={(e) => setTomCnpj(maskCnpj(e.target.value))} />
                  </div>
                </div>
                <ErroBox message={formError} />
                <button type="submit" disabled={saving || !tomNome.trim()} className={BTN}>
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar tomador
                </button>
              </form>
              {tomNovo && (
                <form onSubmit={convidarAdminCliente} className={`${CARD} p-5 space-y-4`}
                  aria-label="Convidar administrador do cliente">
                  <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
                    Convidar administrador do cliente: {tomNovo.nome}
                  </h3>
                  {!convCriado && (
                    <div>
                      <label htmlFor="conv-adm-email" className={LABEL}>E-mail do administrador</label>
                      <input
                        id="conv-adm-email"
                        type="email"
                        className={`${INPUT} ${mostrarErroConvEmail ? '!border-rose-400 dark:!border-rose-600 focus:!ring-rose-500' : ''}`}
                        value={convEmail}
                        required
                        aria-invalid={mostrarErroConvEmail ? 'true' : 'false'}
                        aria-describedby={mostrarErroConvEmail ? 'conv-adm-email-erro' : undefined}
                        onChange={(e) => {
                          setConvEmail(e.target.value)
                          if (convError) setConvError(null)
                        }}
                        onBlur={() => setConvEmailTocado(true)}
                        placeholder="administrador@cliente.com.br"
                      />
                      {mostrarErroConvEmail && (
                        <p id="conv-adm-email-erro" className="text-[11px] font-medium text-rose-600 dark:text-rose-400 mt-1">
                          Por favor, insira um e-mail válido (ex: usuario@dominio.com).
                        </p>
                      )}
                    </div>
                  )}
                  <ErroBox message={convError} />
                  {convCriado ? (
                    <ConviteLink token={convCriado.token} expiraEm={convCriado.expira_em} />
                  ) : (
                    <button
                      type="submit"
                      disabled={convSaving || !convEmail.trim() || (convEmailTocado && !convEmailValido)}
                      className={BTN}
                    >
                      {convSaving && <Loader2 className="w-4 h-4 animate-spin" />}Convidar administrador do cliente
                    </button>
                  )}
                  <button type="button" className={BTN_SEC} onClick={() => setTomNovo(null)}>Fechar</button>
                </form>
              )}
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Nome</th><th className={TH}>CNPJ</th><th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {tomadores.map((t) => (
                      <tr key={t.id}>
                        <td className={`${TD} font-bold`}>{t.nome}</td>
                        <td className={`${TD} font-mono`}>{formatCnpj(t.cnpj) || '—'}</td>
                        <td className={TD}><Situacao ativo={t.ativo} /></td>
                      </tr>
                    ))}
                    {tomadores.length === 0 && (
                      <tr><td className={TD} colSpan={3}>Nenhum tomador cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {aba === 'prestadores' && (
            <>
              <form onSubmit={salvarPrestador} className={`${CARD} p-5 space-y-4`} aria-label="Novo prestador">
                <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">Novo prestador</h3>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <label htmlFor="prest-razao" className={LABEL}>Razão social</label>
                    <input id="prest-razao" className={INPUT} value={prestRazao} required
                      onChange={(e) => setPrestRazao(e.target.value)} />
                  </div>
                  <div>
                    <label htmlFor="prest-cnpj" className={LABEL}>CNPJ</label>
                    <input id="prest-cnpj" className={INPUT} value={prestCnpj} required
                      placeholder="00.000.000/0000-00" inputMode="numeric"
                      onChange={(e) => setPrestCnpj(maskCnpj(e.target.value))} />
                  </div>
                </div>
                <ErroBox message={formError} />
                <button type="submit" disabled={saving || !prestRazao.trim() || !prestCnpj} className={BTN}>
                  {saving && <Loader2 className="w-4 h-4 animate-spin" />}Cadastrar prestador
                </button>
              </form>
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Razão social</th><th className={TH}>CNPJ</th><th className={TH}>Situação</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {prestadores.map((p) => (
                      <tr key={p.id}>
                        <td className={`${TD} font-bold`}>{p.razao_social}</td>
                        <td className={`${TD} font-mono`}>{formatCnpj(p.cnpj)}</td>
                        <td className={TD}><Situacao ativo={p.ativo} /></td>
                      </tr>
                    ))}
                    {prestadores.length === 0 && (
                      <tr><td className={TD} colSpan={3}>Nenhum prestador cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {aba === 'contratos' && (
            <>
              <CadastroTerceirizadaForm
                titulo="Cadastrar terceirizada para um cliente"
                tomadores={tomadores}
                onCadastrada={carregar}
              />
              <ConviteGeradoCard reenvio={reenvio} />
              <div className={`${CARD} overflow-hidden`}>
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[#fbf9fc] dark:bg-[#1f1325] border-b border-[#ebe5ef] dark:border-[#2f1e39]">
                      <th className={TH}>Tomador</th><th className={TH}>Prestador</th>
                      <th className={TH}>CNPJ</th><th className={TH}>Vigência</th><th className={TH}>Situação</th>
                      <th className={TH}>Acesso</th><th className={TH}></th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
                    {contratos.map((c) => (
                      <React.Fragment key={c.id}>
                        <tr>
                          <td className={`${TD} font-bold`}>{c.tomador_nome}</td>
                          <td className={TD}>{c.prestador_razao_social}</td>
                          <td className={`${TD} font-mono`}>{formatCnpj(c.prestador_cnpj)}</td>
                          <td className={TD}>
                            {c.vigencia_inicio || c.vigencia_fim
                              ? `${formatData(c.vigencia_inicio)} a ${formatData(c.vigencia_fim)}`
                              : '—'}
                          </td>
                          <td className={TD}><Situacao ativo={c.ativo} /></td>
                          <td className={TD}><AcessoSelo contrato={c} /></td>
                          <td className={TD}><ReenvioBotao contrato={c} reenvio={reenvio} /></td>
                        </tr>
                        <ReenvioLinha contrato={c} reenvio={reenvio} colSpan={7} />
                      </React.Fragment>
                    ))}
                    {contratos.length === 0 && (
                      <tr><td className={TD} colSpan={7}>Nenhum contrato cadastrado.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

export default OrganizacoesPage
