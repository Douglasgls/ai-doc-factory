import React, { useMemo, useRef, useState } from 'react'
import { Loader2, Plus, Trash2, Undo2 } from 'lucide-react'
import {
  apiService,
  type ParametroEntrada,
  type PerfilJornadaDetalhe,
  type Prestador,
} from '../services/api'
import { BTN, BTN_SEC, CARD, ErroBox, INPUT, LABEL } from './formUi'
import { CampoValor } from './CampoValor'
import { AbasTema, type AbaDef } from './AbasTema'
import { idAba, idPainel } from '../utils/abas'
import {
  GRUPOS,
  fraseValor,
  frasePorData,
  type DefParametro,
} from '../utils/convencoes'
import {
  BASE_LEGAL_MAX,
  NOME_MAX,
  SINDICATO_MAX,
  alteracoesPorGrupo,
  errosPorAba,
  localizarErros,
  resumoErros,
  chaveParametros,
  entradaVazia,
  escopoParaCorpo,
  estadoInicial,
  validarForm,
  valorParaEntrada,
  type Alteracao,
  type Datada,
  type Entrada,
  type Escopo,
  type EstadoForm,
} from '../utils/convencaoForm'

const SUAVE = 'text-[#6e6378] dark:text-[#a093a8]'

const AJUDA_BASE = 'Cite a cláusula da convenção que muda este valor, ex.: CCT 2026/2027, cláusula 12ª.'

const Erro: React.FC<{ id: string; texto?: string }> = ({ id, texto }) =>
  texto ? (
    <p id={id} className="text-xs mt-1 text-red-600 dark:text-red-400">
      {texto}
    </p>
  ) : null

interface Props {
  /** Convenção existente (edição) ou null (cadastro). */
  existente: PerfilJornadaDetalhe | null
  padrao: PerfilJornadaDetalhe
  /** A plataforma escolhe o escopo; o admin de empresa própria cadastra só as dele. */
  plataforma: boolean
  prestadores: Prestador[]
  onCancelar: () => void
  onSalvo: (perfil: string) => void
}

export const ConvencaoForm: React.FC<Props> = ({ existente, padrao, plataforma, prestadores, onCancelar, onSalvo }) => {
  const inicial = useMemo(() => estadoInicial(existente, 'geral'), [existente])
  const [estado, setEstado] = useState<EstadoForm>(inicial)
  const [erros, setErros] = useState<Record<string, string>>({})
  const [erroGeral, setErroGeral] = useState<string | null>(null)
  const [salvando, setSalvando] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  const [recemAberto, setRecemAberto] = useState<string | null>(null)
  const [aba, setAba] = useState<string>(GRUPOS[0].id)
  const [tentouSalvar, setTentouSalvar] = useState(false)

  // o erro de um campo some assim que a pessoa volta a mexer nele
  const limpar = (prefixo: string) =>
    setErros((er) => (Object.keys(er).some((k) => k.startsWith(prefixo)) ? Object.fromEntries(Object.entries(er).filter(([k]) => !k.startsWith(prefixo))) : er))
  const campo = <K extends keyof EstadoForm>(k: K, v: EstadoForm[K]) => {
    limpar(k === 'vigencia_inicio' || k === 'vigencia_fim' ? 'vigencia' : k === 'prestador_id' ? 'prestador' : k)
    setEstado((e) => ({ ...e, [k]: v }))
  }
  const alterar = (chave: string, f: (a: Alteracao) => Alteracao) => {
    limpar(`${chave}:`)
    setEstado((e) => ({ ...e, alteracoes: { ...e.alteracoes, [chave]: f(e.alteracoes[chave]) } }))
  }

  const abrir = (d: DefParametro) => {
    const base = padrao.efetivo[d.chave]
    setRecemAberto(d.chave)
    setEstado((e) => ({
      ...e,
      alteracoes: {
        ...e.alteracoes,
        [d.chave]: { valor: base ? valorParaEntrada(d.tipo, base.valor) : entradaVazia(), base_legal: '', datadas: [] },
      },
    }))
  }
  const desfazer = (chave: string) => {
    setEstado((e) => {
      const resto = { ...e.alteracoes }
      delete resto[chave]
      return { ...e, alteracoes: resto }
    })
    setErros((er) => Object.fromEntries(Object.entries(er).filter(([k]) => !k.startsWith(`${chave}:`))))
  }
  const addDatada = (d: DefParametro) =>
    setEstado((e) => {
      const alt = e.alteracoes[d.chave]
      const nova: Datada = { id: e.proximoId, desde: '', valor: alt.valor, base_legal: '' }
      return {
        ...e,
        proximoId: e.proximoId + 1,
        alteracoes: { ...e.alteracoes, [d.chave]: { ...alt, datadas: [...alt.datadas, nova] } },
      }
    })

  const salvar = async (ev: React.FormEvent) => {
    ev.preventDefault()
    const r = validarForm(estado, padrao.efetivo, plataforma)
    setErros(r.erros)
    setErroGeral(null)
    if (Object.keys(r.erros).length > 0) {
      setTentouSalvar(true)
      // abre a aba do primeiro campo com erro, rola até ele e põe o foco nele
      const primeiro = localizarErros(r.erros)[0]
      if (primeiro.aba) setAba(primeiro.aba)
      requestAnimationFrame(() => {
        const el = document.getElementById(primeiro.campoId)
        el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
        el?.focus({ preventScroll: true })
      })
      return
    }
    const inicialParametros = validarForm(inicial, padrao.efetivo, plataforma).parametros
    const mudaram = chaveParametros(r.parametros) !== chaveParametros(inicialParametros)
    if (existente && mudaram && r.parametros.length === 0) {
      setErroGeral('Uma convenção salva precisa de ao menos uma regra diferente do Padrão.')
      return
    }
    const parametros: ParametroEntrada[] | undefined = r.parametros.length > 0 && (mudaram || !existente) ? r.parametros : undefined
    const escopo = plataforma ? escopoParaCorpo(estado) : {}
    const cadastro = {
      nome: estado.nome.trim(),
      sindicato: estado.sindicato.trim() || null,
      vigencia_inicio: estado.vigencia_inicio || null,
      vigencia_fim: estado.vigencia_fim || null,
      ...escopo,
    }
    setSalvando(true)
    try {
      let perfil = existente?.perfil ?? ''
      if (existente) {
        await apiService.atualizarPerfilJornada(perfil, { ...cadastro, parametros })
      } else {
        perfil = (await apiService.criarPerfilJornada(cadastro)).perfil
        if (parametros) await apiService.atualizarPerfilJornada(perfil, { parametros })
      }
      onSalvo(perfil)
    } catch (err) {
      setErroGeral(err instanceof Error ? err.message : 'Erro ao salvar a convenção')
    } finally {
      setSalvando(false)
    }
  }

  const idTitulo = 'form-convencao-titulo'
  const contagemErros = errosPorAba(erros)
  const contagemAlt = alteracoesPorGrupo(estado.alteracoes)
  const abas: AbaDef[] = GRUPOS.map((g) => ({ id: g.id, rotulo: g.titulo, contagem: contagemAlt[g.id], erro: contagemErros[g.id] > 0 }))
  const resumo = resumoErros(erros)

  return (
    <form ref={formRef} onSubmit={salvar} noValidate className="space-y-5" aria-labelledby={idTitulo}>
      <h2 id={idTitulo} className="text-lg font-bold text-[#2d0a33] dark:text-white">
        {existente ? `Editar ${existente.nome}` : 'Nova convenção'}
      </h2>

      <section className={`${CARD} p-5 space-y-4`} aria-label="Cadastro">
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className={LABEL} htmlFor="conv-nome">Nome</label>
            <input
              id="conv-nome"
              className={INPUT}
              value={estado.nome}
              maxLength={NOME_MAX}
              placeholder="Ex.: Comerciários SP 2026/2027"
              aria-invalid={!!erros.nome || undefined}
              aria-describedby={erros.nome ? 'conv-nome-erro' : undefined}
              onChange={(e) => campo('nome', e.target.value)}
            />
            <Erro id="conv-nome-erro" texto={erros.nome} />
          </div>
          <div>
            <label className={LABEL} htmlFor="conv-sindicato">Sindicato ou categoria</label>
            <input
              id="conv-sindicato"
              className={INPUT}
              value={estado.sindicato}
              maxLength={SINDICATO_MAX}
              placeholder="Ex.: Sindicato dos Comerciários de SP"
              aria-invalid={!!erros.sindicato || undefined}
              aria-describedby={erros.sindicato ? 'conv-sindicato-erro' : undefined}
              onChange={(e) => campo('sindicato', e.target.value)}
            />
            <Erro id="conv-sindicato-erro" texto={erros.sindicato} />
          </div>
          <div>
            <label className={LABEL} htmlFor="conv-inicio">Vigência: início</label>
            <input
              id="conv-inicio"
              type="date"
              className={INPUT}
              value={estado.vigencia_inicio}
              onChange={(e) => campo('vigencia_inicio', e.target.value)}
            />
          </div>
          <div>
            <label className={LABEL} htmlFor="conv-fim">Vigência: fim</label>
            <input
              id="conv-fim"
              type="date"
              className={INPUT}
              value={estado.vigencia_fim}
              aria-invalid={!!erros.vigencia_fim || undefined}
              aria-describedby={erros.vigencia_fim ? 'conv-fim-erro' : undefined}
              onChange={(e) => campo('vigencia_fim', e.target.value)}
            />
            <Erro id="conv-fim-erro" texto={erros.vigencia_fim} />
          </div>
        </div>
        <p className={`text-xs ${SUAVE}`}>Deixe a vigência em branco se a convenção não tem prazo.</p>

        {plataforma && (
          <fieldset className="space-y-2">
            <legend className={LABEL}>Quem usa esta convenção</legend>
            {(
              [
                ['geral', 'Geral (todos os clientes)'],
                ['prestador', 'De um prestador'],
                ['plataforma', 'Só plataforma'],
              ] as [Escopo, string][]
            ).map(([valor, texto]) => (
              <label key={valor} className="flex items-center gap-2 text-sm text-[#2d0a33] dark:text-[#f8f5fc] cursor-pointer">
                <input
                  type="radio"
                  name="conv-escopo"
                  className="accent-[#3e0b48] dark:accent-[#9917a2]"
                  checked={estado.escopo === valor}
                  onChange={() => campo('escopo', valor)}
                />
                {texto}
              </label>
            ))}
            {estado.escopo === 'prestador' && (
              <div className="pl-6">
                <label className={LABEL} htmlFor="conv-prestador">Prestador</label>
                <select
                  id="conv-prestador"
                  className={`${INPUT} max-w-sm`}
                  value={estado.prestador_id}
                  aria-invalid={!!erros.prestador || undefined}
                  aria-describedby={erros.prestador ? 'conv-prestador-erro' : undefined}
                  onChange={(e) => campo('prestador_id', e.target.value)}
                >
                  <option value="">Escolha o prestador</option>
                  {prestadores.map((p) => (
                    <option key={p.id} value={p.id}>{p.razao_social}</option>
                  ))}
                </select>
                <Erro id="conv-prestador-erro" texto={erros.prestador} />
              </div>
            )}
          </fieldset>
        )}
      </section>

      <div className="space-y-4">
      <AbasTema base="form" rotulo="Regras por tema" abas={abas} ativa={aba} onChange={setAba} />
      {GRUPOS.map((g) => (
        <div
          key={g.id}
          role="tabpanel"
          id={idPainel('form', g.id)}
          aria-labelledby={idAba('form', g.id)}
          hidden={g.id !== aba}
        >
        <section className={`${CARD} p-5`} aria-labelledby={`form-grupo-${g.id}`}>
          <h3 id={`form-grupo-${g.id}`} className="text-sm font-bold text-[#2d0a33] dark:text-white">{g.titulo}</h3>
          <div className="mt-2 divide-y divide-[#ebe5ef] dark:divide-[#2f1e39]">
            {g.parametros
              .filter((d) => padrao.efetivo[d.chave])
              .map((d) => {
                const pad = padrao.efetivo[d.chave]
                const alt = estado.alteracoes[d.chave]
                const tevePadraoComData = (pad.vigencias?.length ?? 0) > 0
                return (
                  <div key={d.chave} className="py-3">
                    <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
                      <div>
                        <span className="text-sm text-[#2d0a33] dark:text-[#f8f5fc]">{d.rotulo}</span>
                        <span className={`text-xs ml-3 tabular-nums ${SUAVE}`}>Padrão: {fraseValor(d.chave, pad.valor)}</span>
                      </div>
                      {alt ? (
                        <button type="button" onClick={() => desfazer(d.chave)} className={BTN_SEC}>
                          <Undo2 className="w-3.5 h-3.5" aria-hidden="true" />
                          Desfazer<span className="sr-only">: {d.rotulo}</span>
                        </button>
                      ) : (
                        <button type="button" onClick={() => abrir(d)} className={BTN_SEC}>
                          Alterar<span className="sr-only">: {d.rotulo}</span>
                        </button>
                      )}
                    </div>

                    {alt && (
                      <div className="abrir-alteracao mt-3 ml-1 pl-4 border-l-2 border-[#d9c2de] dark:border-[#5a2a66] space-y-3">
                        <div>
                          <span className={`${LABEL} !mb-1.5`} id={`rot-${d.chave}`}>Valor desta convenção</span>
                          <CampoValor
                            id={`val-${d.chave}`}
                            tipo={d.tipo}
                            rotulo={d.rotulo}
                            valor={alt.valor}
                            onChange={(v) => alterar(d.chave, (a) => ({ ...a, valor: v }))}
                            invalido={!!erros[`${d.chave}:valor`]}
                            erroId={erros[`${d.chave}:valor`] ? `${d.chave}-valor-erro` : undefined}
                            autoFocus={recemAberto === d.chave}
                          />
                          <Erro id={`${d.chave}-valor-erro`} texto={erros[`${d.chave}:valor`]} />
                        </div>
                        <div>
                          <label className={LABEL} htmlFor={`base-${d.chave}`}>Base legal (obrigatória)</label>
                          <p id={`base-${d.chave}-ajuda`} className={`text-xs mb-1.5 ${SUAVE}`}>{AJUDA_BASE}</p>
                          <input
                            id={`base-${d.chave}`}
                            className={INPUT}
                            value={alt.base_legal}
                            maxLength={BASE_LEGAL_MAX}
                            placeholder="Ex.: CCT 2026/2027, cláusula 12ª"
                            aria-required="true"
                            aria-invalid={!!erros[`${d.chave}:base`] || undefined}
                            aria-describedby={`base-${d.chave}-ajuda${erros[`${d.chave}:base`] ? ` ${d.chave}-base-erro` : ''}`}
                            onChange={(e) => alterar(d.chave, (a) => ({ ...a, base_legal: e.target.value }))}
                          />
                          <Erro id={`${d.chave}-base-erro`} texto={erros[`${d.chave}:base`]} />
                        </div>
                        {tevePadraoComData && (
                          <p className={`text-xs ${SUAVE}`}>
                            O Padrão tem mudanças com data ({pad.vigencias?.map((v) => frasePorData(d.chave, v.desde, v.valor)).join('; ')}).
                            Ao alterar, elas deixam de valer nesta convenção.
                          </p>
                        )}

                        {alt.datadas.map((dt) => {
                          const k = `${d.chave}:${dt.id}`
                          const mudar = (f: (x: Datada) => Datada) =>
                            alterar(d.chave, (a) => ({ ...a, datadas: a.datadas.map((x) => (x.id === dt.id ? f(x) : x)) }))
                          return (
                            <div key={dt.id} className="rounded-xl border border-[#ebe5ef] dark:border-[#2f1e39] p-3 space-y-3">
                              <div className="flex flex-wrap items-start gap-4">
                                <div>
                                  <label className={LABEL} htmlFor={`desde-${k}`}>A partir de</label>
                                  <input
                                    id={`desde-${k}`}
                                    type="date"
                                    className={`${INPUT} !w-44`}
                                    value={dt.desde}
                                    aria-invalid={!!erros[`${k}:desde`] || undefined}
                                    aria-describedby={erros[`${k}:desde`] ? `${k}-desde-erro` : undefined}
                                    onChange={(e) => mudar((x) => ({ ...x, desde: e.target.value }))}
                                  />
                                  <Erro id={`${k}-desde-erro`} texto={erros[`${k}:desde`]} />
                                </div>
                                <div>
                                  <span className={`${LABEL} !mb-1.5`}>Novo valor</span>
                                  <CampoValor
                                    id={`val-${k}`}
                                    tipo={d.tipo}
                                    rotulo={`${d.rotulo} a partir da data`}
                                    valor={dt.valor}
                                    onChange={(v: Entrada) => mudar((x) => ({ ...x, valor: v }))}
                                    invalido={!!erros[`${k}:valor`]}
                                    erroId={erros[`${k}:valor`] ? `${k}-valor-erro` : undefined}
                                  />
                                  <Erro id={`${k}-valor-erro`} texto={erros[`${k}:valor`]} />
                                </div>
                                <button
                                  type="button"
                                  onClick={() => alterar(d.chave, (a) => ({ ...a, datadas: a.datadas.filter((x) => x.id !== dt.id) }))}
                                  className={`${BTN_SEC} sm:mt-5`}
                                >
                                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                                  Remover<span className="sr-only"> mudança com data</span>
                                </button>
                              </div>
                              <div>
                                <label className={LABEL} htmlFor={`base-${k}`}>Base legal (obrigatória)</label>
                                <p id={`base-${k}-ajuda`} className={`text-xs mb-1.5 ${SUAVE}`}>{AJUDA_BASE}</p>
                                <input
                                  id={`base-${k}`}
                                  className={INPUT}
                                  value={dt.base_legal}
                                  maxLength={BASE_LEGAL_MAX}
                                  placeholder="Ex.: CCT 2026/2027, aditivo 3"
                                  aria-required="true"
                                  aria-invalid={!!erros[`${k}:base`] || undefined}
                                  aria-describedby={`base-${k}-ajuda${erros[`${k}:base`] ? ` ${k}-base-erro` : ''}`}
                                  onChange={(e) => mudar((x) => ({ ...x, base_legal: e.target.value }))}
                                />
                                <Erro id={`${k}-base-erro`} texto={erros[`${k}:base`]} />
                              </div>
                            </div>
                          )
                        })}

                        <button
                          type="button"
                          onClick={() => addDatada(d)}
                          className="inline-flex items-center gap-1 text-xs font-semibold text-[#5c1363] dark:text-[#f38df9] underline underline-offset-2 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9333ea] rounded"
                        >
                          <Plus className="w-3 h-3" aria-hidden="true" />
                          Adicionar mudança com data
                        </button>
                      </div>
                    )}
                  </div>
                )
              })}
          </div>
        </section>
        </div>
      ))}
      </div>

      <ErroBox message={erroGeral} />
      {tentouSalvar && resumo && (
        <div
          role="alert"
          className="p-3 rounded-xl bg-red-50 dark:bg-red-950/20 border border-red-200 dark:border-red-900/50 text-xs font-medium text-red-600 dark:text-red-400"
        >
          {resumo}
        </div>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" disabled={salvando} className={BTN}>
          {salvando && <Loader2 className="w-4 h-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
          Salvar convenção
        </button>
        <button type="button" onClick={onCancelar} disabled={salvando} className={BTN_SEC}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
