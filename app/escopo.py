"""Escopo de acesso aos dados por nível de usuário. Único lugar que decide quem enxerga o quê; os routers só
declaram a dependência (por rota) ou passam o usuário às listagens.

- plataforma: tudo, leitura e escrita.
- tomador: SÓ LEITURA, lotes cujo contrato é do seu tomador (ativo ou não: é o histórico do cliente).
- prestador: leitura e escrita em lotes de contratos ATIVOS do seu prestador (com tomador e prestador ativos).
- Lote sem contrato: só plataforma. Fora do escopo = 404, igual a inexistente.

Listagens filtram na consulta SQL (`condicao_lote`, `condicao_contrato`); recurso por id passa pelas dependências
`lote_para_leitura`/`lote_para_escrita`/`documento_para_leitura`/`documento_para_escrita`."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import ColumnElement, and_, false, select, true
from sqlalchemy.orm import Session, aliased

from app.database import get_session
from app.models import Contrato, Documento, Lote, Prestador, Tomador
from app.routers.auth.actions import ID_MAX, UsuarioContexto, exigir_plataforma, exigir_usuario  # noqa: F401

METODOS_LEITURA = frozenset({"GET", "HEAD", "OPTIONS"})
_NEGADO_ESCRITA = "somente leitura: usuários do nível tomador não alteram dados"


def filtro_contrato(usuario: UsuarioContexto, c=Contrato, t=Tomador, p=Prestador) -> ColumnElement[bool]:
    """Condição sobre contrato `c` já unido a tomador `t` e prestador `p` (entidades ou aliases)."""
    if usuario.nivel == "plataforma":
        return true()
    if usuario.nivel == "tomador":
        return and_(c.tomador_id == usuario.tomador_id, t.ativo)
    if usuario.nivel == "prestador":
        return and_(c.prestador_id == usuario.prestador_id, c.ativo, t.ativo, p.ativo)
    return false()  # nível desconhecido: falha fechada


def filtro_lote(usuario: UsuarioContexto, lote=Lote) -> ColumnElement[bool]:
    """Condição sobre `lote` (entidade ou alias): o lote está no escopo do usuário."""
    if usuario.nivel == "plataforma":
        return true()
    ce, te, pe = aliased(Contrato), aliased(Tomador), aliased(Prestador)
    return (select(1).select_from(ce).join(te, te.id == ce.tomador_id).join(pe, pe.id == ce.prestador_id)
            .where(ce.id == lote.contrato_id, filtro_contrato(usuario, ce, te, pe)).exists())


def condicao_contrato(usuario: UsuarioContexto, c: str = "c", t: str = "t", p: str = "p") -> tuple[str, list]:
    """Condição SQL sobre contrato `c` já unido a tomador `t` e prestador `p`, e seus parâmetros."""
    if usuario.nivel == "plataforma":
        return "TRUE", []
    if usuario.nivel == "tomador":
        return f"({c}.tomador_id = %s AND {t}.ativo)", [usuario.tomador_id]
    if usuario.nivel == "prestador":
        return f"({c}.prestador_id = %s AND {c}.ativo AND {t}.ativo AND {p}.ativo)", [usuario.prestador_id]
    return "FALSE", []  # nível desconhecido: falha fechada


def condicao_lote(usuario: UsuarioContexto, l: str = "l") -> tuple[str, list]:
    """Condição SQL sobre a tabela `lote` (alias `l`): o lote está no escopo do usuário."""
    if usuario.nivel == "plataforma":
        return "TRUE", []
    cond, args = condicao_contrato(usuario, "ce", "te", "pe")
    return (f"EXISTS (SELECT 1 FROM contrato ce JOIN tomador te ON te.id = ce.tomador_id "
            f"JOIN prestador pe ON pe.id = ce.prestador_id WHERE ce.id = {l}.contrato_id AND {cond})"), args


_PRESTADOR_JA_TEM_ACESSO = "prestador já tem acesso; peça ao administrador dele para convidar"
_PRESTADOR_COM_CONVITE_PENDENTE = "já há convite pendente para este prestador"
_NEGADO_CONVITE = "sem permissão para criar este convite"


def prestador_tem_usuario_ativo(conn, prestador_id: int) -> bool:
    return conn.execute("SELECT 1 FROM usuario WHERE prestador_id = %s AND ativo", (prestador_id,)).fetchone() is not None


def prestador_tem_convite_pendente(conn, prestador_id: int) -> bool:
    return conn.execute("SELECT 1 FROM convite WHERE prestador_id = %s AND usado_em IS NULL AND expira_em > now()",
                        (prestador_id,)).fetchone() is not None


def motivo_recusa_convite(conn, usuario: UsuarioContexto, nivel: str, papel: str,
                          tomador_id: int | None, prestador_id: int | None) -> str | None:
    """Único lugar que decide quem pode convidar quem. None = permitido; senão, o motivo da recusa (403).

    - plataforma: qualquer nível e papel.
    - admin do tomador: tomador (o seu), admin ou membro; e prestador (admin) com contrato ATIVO com o seu tomador,
      SÓ se o prestador não tem usuário ativo (senão a pessoa convidada veria os contratos do prestador com OUTROS
      clientes) e não tem convite pendente de outra organização (idem, para o convite ainda não aceito).
    - admin do prestador: prestador (o seu), admin ou membro.
    - membros e qualquer outro caso: nada. Ninguém de fora da plataforma convida nível plataforma.
    Quem chama deve manter a linha do prestador travada (FOR NO KEY UPDATE) para a checagem valer até o INSERT."""
    if usuario.nivel == "plataforma":
        return None
    if usuario.papel != "admin":
        return _NEGADO_CONVITE
    if usuario.nivel == "tomador" and usuario.tomador_id is not None:
        if nivel == "tomador":
            return None if tomador_id == usuario.tomador_id else _NEGADO_CONVITE
        if nivel == "prestador" and papel == "admin" and prestador_id is not None:
            if conn.execute("SELECT 1 FROM contrato c JOIN tomador t ON t.id = c.tomador_id "
                            "JOIN prestador p ON p.id = c.prestador_id "
                            "WHERE c.tomador_id = %s AND c.prestador_id = %s AND c.ativo AND t.ativo AND p.ativo",
                            (usuario.tomador_id, prestador_id)).fetchone() is None:
                return _NEGADO_CONVITE
            if prestador_tem_usuario_ativo(conn, prestador_id):
                return _PRESTADOR_JA_TEM_ACESSO
            if conn.execute(
                    "SELECT 1 FROM convite c LEFT JOIN usuario u ON u.id = c.criado_por "
                    "WHERE c.prestador_id = %s AND c.usado_em IS NULL AND c.expira_em > now() "
                    "AND u.tomador_id IS DISTINCT FROM %s", (prestador_id, usuario.tomador_id)).fetchone():
                return _PRESTADOR_COM_CONVITE_PENDENTE
            return None
        return _NEGADO_CONVITE
    if usuario.nivel == "prestador" and usuario.prestador_id is not None:
        return None if nivel == "prestador" and prestador_id == usuario.prestador_id else _NEGADO_CONVITE
    return _NEGADO_CONVITE


def pode_convidar(conn, usuario: UsuarioContexto, nivel: str, papel: str,
                  tomador_id: int | None, prestador_id: int | None) -> bool:
    return motivo_recusa_convite(conn, usuario, nivel, papel, tomador_id, prestador_id) is None


def _id_valido(id_: int) -> bool:
    return 1 <= id_ <= ID_MAX


def _checar_escrita(usuario: UsuarioContexto, escrita: bool) -> None:
    if escrita and usuario.nivel not in ("plataforma", "prestador"):
        raise HTTPException(403, _NEGADO_ESCRITA)


def exigir_lote_no_escopo(session: Session, usuario: UsuarioContexto, lote_id: int, escrita: bool = False) -> None:
    """403 se o nível não pode escrever; 404 se o lote não existe ou está fora do escopo."""
    _checar_escrita(usuario, escrita)
    if not _id_valido(lote_id) or session.execute(
            select(Lote.id).where(Lote.id == lote_id, filtro_lote(usuario))).first() is None:
        raise HTTPException(404, "lote não encontrado")


def exigir_documento_no_escopo(session: Session, usuario: UsuarioContexto, documento_id: int,
                               escrita: bool = False) -> None:
    """Idem para documento: vale o escopo do lote a que ele pertence."""
    _checar_escrita(usuario, escrita)
    if not _id_valido(documento_id) or session.execute(
            select(Documento.id).join(Lote, Lote.id == Documento.lote_id)
            .where(Documento.id == documento_id, filtro_lote(usuario))).first() is None:
        raise HTTPException(404, "documento não encontrado")


def exigir_contrato_de_upload(conn, usuario: UsuarioContexto, contrato_id: int | None) -> None:
    """Prestador: contrato_id obrigatório (422) e tem que ser um contrato seu ativo (404). Plataforma: sem exigência
    aqui (a validação de existência/atividade é a de sempre). Tomador não chega aqui (403 antes)."""
    if usuario.nivel == "plataforma":
        return
    _checar_escrita(usuario, True)
    if contrato_id is None:
        raise HTTPException(422, "contrato_id é obrigatório para o upload")
    cond, args = condicao_contrato(usuario)
    if not _id_valido(contrato_id) or conn.execute(
            "SELECT 1 FROM contrato c JOIN tomador t ON t.id = c.tomador_id "
            f"JOIN prestador p ON p.id = c.prestador_id WHERE c.id = %s AND {cond}",
            [contrato_id, *args]).fetchone() is None:
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")


# ---------- dependências do FastAPI ----------

def acesso_a_dados(request: Request, usuario: UsuarioContexto = Depends(exigir_usuario)) -> UsuarioContexto:
    """Nível dos routers de dados: qualquer usuário logado lê (filtrado); tomador nunca escreve (403)."""
    if usuario.nivel == "tomador" and request.method not in METODOS_LEITURA:
        raise HTTPException(403, _NEGADO_ESCRITA)
    return usuario


def _verificar(verificador, escrita: bool, id_: int, usuario: UsuarioContexto, session: Session) -> int:
    verificador(session, usuario, id_, escrita=escrita)
    # Libera a conexão: a checagem é uma transação própria, como antes, e nada fica preso durante um stream SSE.
    session.commit()
    return id_


def lote_para_leitura(lote_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados),
                      session: Session = Depends(get_session)) -> int:
    return _verificar(exigir_lote_no_escopo, False, lote_id, usuario, session)


def lote_para_escrita(lote_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados),
                      session: Session = Depends(get_session)) -> int:
    return _verificar(exigir_lote_no_escopo, True, lote_id, usuario, session)


def documento_para_leitura(documento_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados),
                           session: Session = Depends(get_session)) -> int:
    return _verificar(exigir_documento_no_escopo, False, documento_id, usuario, session)


def documento_para_escrita(documento_id: int, usuario: UsuarioContexto = Depends(acesso_a_dados),
                           session: Session = Depends(get_session)) -> int:
    return _verificar(exigir_documento_no_escopo, True, documento_id, usuario, session)


# Dependências que fecham o acesso por recurso; a varredura de rotas exige uma delas em toda rota com id na URL.
DEPENDENCIAS_DE_RECURSO = (lote_para_leitura, lote_para_escrita, documento_para_leitura, documento_para_escrita)
