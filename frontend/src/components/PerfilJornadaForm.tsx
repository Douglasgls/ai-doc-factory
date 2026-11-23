import React, { useMemo, useState } from 'react'
import { Loader2, Plus, Trash2 } from 'lucide-react'
import { apiService, type ParametroProprio, type PerfilJornadaDetalhe } from '../services/api'
import { BTN, BTN_SEC, CARD, ErroBox, INPUT, LABEL } from './formUi'
import {
  BASE_LEGAL_MAX,
  formatarValor,
  linhasDe,
  nomeUnidade,
  rotuloParametro,
  validarPerfil,
  type LinhaForm,
} from '../utils/perfisJornada'

interface Props {
  /** Perfil existente (edição) ou null (criação). */
  existente: PerfilJornadaDetalhe | null
  /** Parâmetros do clt_padrao (um por nome, com a unidade). */
  catalogo: ParametroProprio[]
  onCancelar: () => void
  onSalvo: (perfil: string) => void
}

export const PerfilJornadaForm: React.FC<Props> = ({ existente, catalogo, onCancelar, onSalvo }) => {
  const [nome, setNome] = useState(existente?.nome ?? '')
  const [linhas, setLinhas] = useState<LinhaForm[]>(existente ? linhasDe(existente.proprios) : [])
  const [proxChave, setProxChave] = useState(existente ? existente.proprios.length : 0)
  const [erro, setErro] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)

  const unidades = useMemo(() => new Map(catalogo.map((c) => [c.parametro, c.unidade])), [catalogo])
  const padrao = useMemo(() => new Map(catalogo.map((c) => [c.parametro, c])), [catalogo])
  const validos = useMemo(() => new Set(unidades.keys()), [unidades])

  const atualizar = (chave: number, campo: keyof LinhaForm, valor: string) =>
    setLinhas((ls) => ls.map((l) => (l.chave === chave ? { ...l, [campo]: valor } : l)))

  const adicionar = () => {
    setLinhas((ls) => [...ls, { chave: proxChave, parametro: '', valor: '', base_legal: '', vigente_desde: '' }])
    setProxChave(proxChave + 1)
  }

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault()
    const r = validarPerfil(nome.trim(), linhas, validos)
    if ('erro' in r) {
      setErro(r.erro)
      return
    }
    setErro(null)
    setSalvando(true)
    try {
      const params = r.parametros.length ? r.parametros : undefined
      let perfil = existente?.perfil ?? ''
      if (!existente) perfil = (await apiService.criarPerfilJornada({ nome: nome.trim() })).perfil
      if (existente || params) {
        await apiService.atualizarPerfilJornada(perfil, { nome: nome.trim(), parametros: params })
      }
      onSalvo(perfil)
    } catch (err) {
      setErro(err instanceof Error ? err.message : 'Erro ao salvar o perfil de jornada')
    } finally {
      setSalvando(false)
    }
  }

  return (
    <form onSubmit={salvar} className={`${CARD} p-5 space-y-4`} noValidate>
      <div>
        <h3 className="text-sm font-bold text-[#2d0a33] dark:text-white">
          {existente ? `Editar ${existente.nome}` : 'Nova convenção'}
        </h3>
        <p className="text-xs text-[#877991] dark:text-[#a093a8] mt-0.5">
          Informe só o que difere do Padrão; o resto é herdado. Salvar substitui todos os parâmetros próprios da
          convenção. Cada parâmetro informado substitui a linha do tempo inteira dele no padrão (inclusive as vigências da EC
          141) e precisa de uma linha de base, sem vigência.
        </p>
      </div>

      <div className="max-w-sm">
        <label className={LABEL} htmlFor="perfil-nome">Nome da convenção</label>
        <input
          id="perfil-nome"
          className={INPUT}
          value={nome}
          maxLength={100}
          placeholder="Ex.: Comerciários SP 2026/2027"
          onChange={(e) => setNome(e.target.value)}
        />
      </div>

      <div className="space-y-3">
        {linhas.length === 0 && (
          <p className="text-xs text-[#877991] dark:text-[#a093a8]">Nenhum parâmetro próprio: a convenção usa os valores do Padrão.</p>
        )}
        {linhas.map((l, i) => {
          const unidade = unidades.get(l.parametro)
          const ref = padrao.get(l.parametro)
          const v = Number(l.valor.trim().replace(',', '.'))
          return (
            <div
              key={l.chave}
              className="grid grid-cols-1 md:grid-cols-12 gap-3 p-3 rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39]"
            >
              <div className="md:col-span-3">
                <label className={LABEL} htmlFor={`par-${l.chave}`}>Parâmetro</label>
                <select
                  id={`par-${l.chave}`}
                  className={INPUT}
                  value={l.parametro}
                  onChange={(e) => atualizar(l.chave, 'parametro', e.target.value)}
                >
                  <option value="">Escolha…</option>
                  {catalogo.map((c) => (
                    <option key={c.parametro} value={c.parametro}>{rotuloParametro(c.parametro)}</option>
                  ))}
                </select>
                {ref && unidade && (
                  <p className="text-[11px] text-[#877991] dark:text-[#a093a8] mt-1">
                    Padrão: {formatarValor(l.parametro, ref.valor, unidade)}
                  </p>
                )}
              </div>
              <div className="md:col-span-2">
                <label className={LABEL} htmlFor={`val-${l.chave}`}>
                  Valor{unidade ? ` (${nomeUnidade(unidade)})` : ''}
                </label>
                <input
                  id={`val-${l.chave}`}
                  className={INPUT}
                  inputMode="decimal"
                  value={l.valor}
                  onChange={(e) => atualizar(l.chave, 'valor', e.target.value)}
                />
                {unidade && l.valor.trim() !== '' && Number.isFinite(v) && v >= 0 && (
                  <p className="text-[11px] text-[#877991] dark:text-[#a093a8] mt-1">
                    = {formatarValor(l.parametro, v, unidade)}
                  </p>
                )}
              </div>
              <div className="md:col-span-4">
                <label className={LABEL} htmlFor={`bl-${l.chave}`}>Base legal</label>
                <input
                  id={`bl-${l.chave}`}
                  className={INPUT}
                  value={l.base_legal}
                  maxLength={BASE_LEGAL_MAX}
                  placeholder="ex.: EC 141/2026, art. 9º"
                  onChange={(e) => atualizar(l.chave, 'base_legal', e.target.value)}
                />
              </div>
              <div className="md:col-span-2">
                <label className={LABEL} htmlFor={`vig-${l.chave}`}>Vigente desde</label>
                <input
                  id={`vig-${l.chave}`}
                  type="date"
                  className={INPUT}
                  value={l.vigente_desde}
                  onChange={(e) => atualizar(l.chave, 'vigente_desde', e.target.value)}
                />
                <p className="text-[11px] text-[#877991] dark:text-[#a093a8] mt-1">Vazio = valor de base</p>
              </div>
              <div className="md:col-span-1 flex md:items-end">
                <button
                  type="button"
                  aria-label={`Remover linha ${i + 1}`}
                  onClick={() => setLinhas((ls) => ls.filter((x) => x.chave !== l.chave))}
                  className={BTN_SEC}
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )
        })}
        <button type="button" onClick={adicionar} className={BTN_SEC}>
          <Plus className="w-3.5 h-3.5" />
          Adicionar parâmetro
        </button>
      </div>

      <ErroBox message={erro} />

      <div className="flex items-center gap-3">
        <button type="submit" disabled={salvando} className={BTN}>
          {salvando && <Loader2 className="w-4 h-4 animate-spin" />}
          Salvar convenção
        </button>
        <button type="button" onClick={onCancelar} disabled={salvando} className={BTN_SEC}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
