"""Perfis de jornada (Goal 6) e a associação ao contrato. Ler perfis, criar/editar os do seu escopo e escolher o do
próprio contrato: a plataforma e o admin de empresa própria (app/escopo.py decide quais perfis cada um vê e edita).
A herança e a vigência por data ficam em app/ponto.py; aqui só se grava e se lê. O cadastro (nome, sindicato,
vigência e escopo) fica em `perfil_jornada_cadastro`; os parâmetros, em `perfil_jornada`."""
import re
import unicodedata
from datetime import date

from fastapi import HTTPException
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app import ponto
from app.escopo import (exigir_perfil_editavel, exigir_perfil_no_escopo, filtro_contrato, filtro_perfil,
                        perfil_nao_encontrado)
from app.models import Contrato, PerfilJornada, PerfilJornadaCadastro, Prestador, Tomador
from app.routers.auth.actions import UsuarioContexto
from app.routers.organizacoes import actions as organizacoes
from app.routers.perfis_jornada.schemas import PerfilEntrada, PerfilNovo, vigencia_coerente

SLUG_MAX = 40  # a base do slug deixa espaço para o sufixo numérico dentro do limite de 50 do padrão
SLUG_MAX_FINAL = 50
_CAMPOS_CADASTRO = ("nome", "sindicato", "vigencia_inicio", "vigencia_fim", "geral", "prestador_id")
_CAMPOS_ESCOPO = frozenset({"geral", "prestador_id"})  # só a plataforma envia
_NEGADO_ESCOPO = "apenas a plataforma define se o perfil é geral ou de qual prestador"
_COLUNAS = (PerfilJornada.parametro, PerfilJornada.valor, PerfilJornada.base_legal, PerfilJornada.vigente_desde,
            PerfilJornada.unidade)


def _linhas(session: Session, perfil: str) -> list:
    return list(session.execute(
        select(*_COLUNAS).where(PerfilJornada.perfil == perfil)
        .order_by(PerfilJornada.parametro, PerfilJornada.vigente_desde.asc().nulls_first())))


def nome_do_slug(perfil: str) -> str:
    """Nome de um perfil sem cadastro: o slug legível ("adm_publica" -> "Adm publica")."""
    texto = perfil.replace("_", " ")
    return texto[:1].upper() + texto[1:]


def gerar_slug(nome: str) -> str:
    """Slug base do nome: minúsculas, sem acento, só `[a-z0-9_]`, até SLUG_MAX caracteres."""
    ascii_ = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_.lower()).strip("_")[:SLUG_MAX].strip("_")
    return slug or "perfil"


def vigente(inicio: date | None, fim: date | None, hoje: date | None = None) -> bool:
    """Hoje está dentro da vigência; início e fim vazios = sempre vigente."""
    hoje = hoje or date.today()
    return (inicio is None or inicio <= hoje) and (fim is None or hoje <= fim)


def _cadastro(session: Session, perfil: str) -> dict | None:
    c = session.get(PerfilJornadaCadastro, perfil)
    return None if c is None else {k: getattr(c, k) for k in _CAMPOS_CADASTRO}


def _cadastro_out(perfil: str, c: dict | None, usuario: UsuarioContexto) -> dict:
    """Perfil sem linha de cadastro (criado por fora da API) sai com o nome do slug, não geral e sem dono."""
    c = c or {"nome": nome_do_slug(perfil), "sindicato": None, "vigencia_inicio": None, "vigencia_fim": None,
              "geral": False, "prestador_id": None}
    dono_visivel = usuario.nivel == "plataforma" or c["prestador_id"] == usuario.prestador_id
    editavel = perfil != ponto.PERFIL_PADRAO and (
        usuario.nivel == "plataforma" or (c["prestador_id"] is not None and dono_visivel))
    return {**c, "prestador_id": c["prestador_id"] if dono_visivel else None, "editavel": editavel,
            "vigente": vigente(c["vigencia_inicio"], c["vigencia_fim"])}


def _existe(session: Session, perfil: str) -> bool:
    return (session.get(PerfilJornadaCadastro, perfil) is not None or session.execute(
        select(PerfilJornada.id).where(PerfilJornada.perfil == perfil).limit(1)).first() is not None)


def _perfil(session: Session, perfil: str, usuario: UsuarioContexto) -> dict:
    exigir_perfil_no_escopo(session, usuario, perfil)
    padrao = _linhas(session, ponto.PERFIL_PADRAO)
    proprios = padrao if perfil == ponto.PERFIL_PADRAO else _linhas(session, perfil)
    if not proprios and not _existe(session, perfil):
        raise perfil_nao_encontrado(perfil)
    return {
        "perfil": perfil, "padrao": perfil == ponto.PERFIL_PADRAO,
        **_cadastro_out(perfil, _cadastro(session, perfil), usuario),
        "proprios": [{"parametro": p, "valor": float(v), "unidade": u, "base_legal": b, "vigente_desde": d}
                     for p, v, b, d, u in proprios],
        "efetivo": ponto.herdar([tuple(l)[:4] for l in padrao], [tuple(l)[:4] for l in proprios]),
    }


def listar_perfis(session: Session, usuario: UsuarioContexto) -> list[dict]:
    consulta = (select(Contrato.perfil_jornada, func.count())
                .join(Tomador, Tomador.id == Contrato.tomador_id).join(Prestador, Prestador.id == Contrato.prestador_id)
                .where(filtro_contrato(usuario)))
    contratos = {nome: n for nome, n in session.execute(consulta.group_by(Contrato.perfil_jornada))}
    parametros = {nome: n for nome, n in session.execute(
        select(PerfilJornada.perfil, func.count(func.distinct(PerfilJornada.parametro))).group_by(PerfilJornada.perfil))}
    cadastros = {c.perfil: {k: getattr(c, k) for k in _CAMPOS_CADASTRO}
                 for c in session.scalars(select(PerfilJornadaCadastro).where(filtro_perfil(usuario)))}
    nomes = set(cadastros)
    if usuario.nivel == "plataforma":
        nomes |= set(parametros)  # perfis sem cadastro (por fora da API): só a plataforma
    return [{"perfil": nome, "padrao": nome == ponto.PERFIL_PADRAO, "parametros_proprios": parametros.get(nome, 0),
             "contratos": contratos.get(nome, 0), **_cadastro_out(nome, cadastros.get(nome), usuario)}
            for nome in sorted(nomes)]


def obter_perfil(session: Session, perfil: str, usuario: UsuarioContexto) -> dict:
    return _perfil(session, perfil, usuario)


def _exigir_prestador(session: Session, prestador_id: int) -> None:
    if session.execute(select(Prestador.id).where(Prestador.id == prestador_id)).first() is None:
        raise HTTPException(404, f"prestador {prestador_id} não encontrado")


def _recusar_escopo_de_quem_nao_e_plataforma(usuario: UsuarioContexto, corpo) -> None:
    """Só a plataforma envia `geral` e `prestador_id`: o admin de empresa própria cria perfis que nascem dele e
    nunca gerais (qualquer um dos dois campos no corpo dele dá 403, mesmo que seja o valor atual)."""
    if usuario.nivel != "plataforma" and corpo.model_fields_set & _CAMPOS_ESCOPO:
        raise HTTPException(403, _NEGADO_ESCOPO)


def criar_perfil(session: Session, corpo: PerfilNovo, usuario: UsuarioContexto) -> dict:
    """Cria um perfil sem parâmetros próprios (herda tudo de `clt_padrao`) com o slug gerado a partir do nome:
    `slug`, `slug_2`, `slug_3`... em colisão. A chave primária decide corridas entre criações simultâneas.
    Plataforma: geral e/ou de um prestador (ou nenhum dos dois). Admin de empresa própria: sempre dele, nunca geral."""
    _recusar_escopo_de_quem_nao_e_plataforma(usuario, corpo)
    if usuario.nivel == "plataforma":
        geral, dono = bool(corpo.geral), corpo.prestador_id
        if dono is not None:
            _exigir_prestador(session, dono)
    else:
        geral, dono = False, usuario.prestador_id
    base = gerar_slug(corpo.nome)
    for n in range(1, 1000):
        sufixo = "" if n == 1 else f"_{n}"
        slug = base[:SLUG_MAX_FINAL - len(sufixo)] + sufixo
        if _existe(session, slug):
            continue
        criado = session.execute(
            pg_insert(PerfilJornadaCadastro).values(
                perfil=slug, nome=corpo.nome, sindicato=corpo.sindicato, vigencia_inicio=corpo.vigencia_inicio,
                vigencia_fim=corpo.vigencia_fim, geral=geral, prestador_id=dono)
            .on_conflict_do_nothing().returning(PerfilJornadaCadastro.perfil)).first()
        if criado is not None:
            resultado = _perfil(session, slug, usuario)
            session.commit()
            return resultado
    raise HTTPException(409, "não foi possível gerar um identificador único para o perfil")


def _gravar_cadastro(session: Session, perfil: str, corpo: PerfilEntrada) -> None:
    """Cria ou atualiza o cadastro: só os campos enviados mudam. Perfil novo sem nome recebe o nome do slug."""
    atual = _cadastro(session, perfil)
    novo = dict(atual or {k: v for k, v in _cadastro_out(perfil, None, _PLATAFORMA).items() if k in _CAMPOS_CADASTRO})
    novo.update({k: getattr(corpo, k) for k in corpo.model_fields_set & set(_CAMPOS_CADASTRO)})
    if novo["nome"] is None or novo["geral"] is None:
        raise HTTPException(422, "nome e geral não podem ser nulos")
    try:  # a vigência final pode misturar o que veio com o que já estava gravado
        vigencia_coerente(novo["vigencia_inicio"], novo["vigencia_fim"])
    except ValueError as erro:
        raise HTTPException(422, str(erro))
    if novo["prestador_id"] is not None and novo["prestador_id"] != (atual or {}).get("prestador_id"):
        _exigir_prestador(session, novo["prestador_id"])
    if atual != novo:
        session.execute(pg_insert(PerfilJornadaCadastro).values(perfil=perfil, **novo).on_conflict_do_update(
            index_elements=[PerfilJornadaCadastro.perfil], set_=novo))


# Contexto só para montar o cadastro padrão de um perfil novo criado pela plataforma (não vaza para nenhuma resposta).
_PLATAFORMA = UsuarioContexto(id=0, email="", nome="", nivel="plataforma", papel="admin", tomador_id=None,
                              prestador_id=None)


def gravar_perfil(session: Session, perfil: str, corpo: PerfilEntrada, usuario: UsuarioContexto) -> dict:
    """Cria o perfil ou substitui TODOS os seus parâmetros próprios (idempotente), e atualiza nome, sindicato,
    vigência e (só a plataforma) escopo quando enviados. Sem `parametros`, edita só o cadastro de um perfil
    existente. O perfil padrão não é alterado pela API: ele é a referência legal e muda só por migração.
    O admin de empresa própria só edita perfis dele (404 fora do escopo, 403 em geral ou de outro dono) e não cria
    por PUT (use POST); a plataforma cria por PUT, como antes."""
    if perfil == ponto.PERFIL_PADRAO:
        exigir_perfil_no_escopo(session, usuario, perfil)
        raise HTTPException(409, f"o perfil '{ponto.PERFIL_PADRAO}' é a referência e não é alterado pela API")
    exigir_perfil_editavel(session, usuario, perfil)
    _recusar_escopo_de_quem_nao_e_plataforma(usuario, corpo)
    if corpo.parametros is None:
        if not _existe(session, perfil):
            raise HTTPException(422, "parametros é obrigatório para criar um perfil")
        _gravar_cadastro(session, perfil, corpo)
        resultado = _perfil(session, perfil, usuario)
        session.commit()
        return resultado
    unidades = {p: u for p, u in session.execute(
        select(PerfilJornada.parametro, PerfilJornada.unidade)
        .where(PerfilJornada.perfil == ponto.PERFIL_PADRAO, PerfilJornada.vigente_desde.is_(None)))}
    desconhecidos = sorted({p.parametro for p in corpo.parametros} - set(unidades))
    if desconhecidos:
        raise HTTPException(422, f"parâmetro desconhecido: {', '.join(desconhecidos)}; "
                                 f"válidos: {', '.join(sorted(unidades))}")
    _gravar_cadastro(session, perfil, corpo)
    session.execute(delete(PerfilJornada).where(PerfilJornada.perfil == perfil)
                    .execution_options(synchronize_session=False))
    session.execute(insert(PerfilJornada), [
        {"perfil": perfil, "parametro": p.parametro, "valor": p.valor, "unidade": unidades[p.parametro],
         "base_legal": p.base_legal, "vigente_desde": p.vigente_desde} for p in corpo.parametros])
    resultado = _perfil(session, perfil, usuario)
    session.commit()
    return resultado


def associar_perfil(session: Session, contrato_id: int, perfil: str, usuario: UsuarioContexto) -> dict:
    """Aponta o contrato para o perfil. Vale para as análises feitas a partir daí; as já gravadas não mudam
    (cada uma guarda o perfil que usou) até o documento ser reprocessado. O admin de empresa própria só escolhe um
    perfil que ele vê (o Padrão, os gerais e os dele); outro dá 404, como inexistente."""
    if perfil != ponto.PERFIL_PADRAO:
        exigir_perfil_no_escopo(session, usuario, perfil)
        if not _existe(session, perfil):
            raise perfil_nao_encontrado(perfil)
    if session.execute(update(Contrato).where(Contrato.id == contrato_id).values(perfil_jornada=perfil)
                       .returning(Contrato.id)).first() is None:
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")
    linha = session.execute(organizacoes._select_contrato(usuario).where(Contrato.id == contrato_id)).one()
    session.commit()
    return organizacoes._contrato(linha)
