"""Convites: link de uso único. O token (secrets.token_urlsafe) só existe na resposta da criação; o banco guarda
o sha256. As rotas públicas respondem 404 com o MESMO corpo para token inexistente, usado, expirado ou de
organização desativada. O token nunca vai para log, mensagem de erro nem resposta de listagem."""
import hashlib
import secrets
from datetime import timedelta

import psycopg
from fastapi import HTTPException
from sqlalchemy import case, exists, func, insert, select, true, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config, senhas
from app.escopo import filtro_convite_gerenciavel, motivo_recusa_convite, prestador_tem_usuario_ativo
from app.models import Convite, Prestador, Tomador, Usuario
from app.routers.auth.actions import UsuarioContexto, emitir_token
from app.routers.convites.schemas import AceiteIn, NovoConvite

NAO_ENCONTRADO = "convite inválido, usado ou expirado"
TOKEN_MAX = 200  # token_urlsafe(32) tem 43 caracteres; acima disto nem consulta o banco

# Organização do convite ainda ativa (convite de plataforma não tem organização: conta como ativa).
_ORG_ATIVA = func.coalesce(select(Tomador.ativo).where(Tomador.id == Convite.tomador_id).scalar_subquery(),
                           select(Prestador.ativo).where(Prestador.id == Convite.prestador_id).scalar_subquery(),
                           true())
# Convite utilizável: não usado, não expirado e com a organização ativa.
_UTILIZAVEL = (Convite.usado_em.is_(None), Convite.expira_em > func.now(), _ORG_ATIVA)
_NOME_ORG = func.coalesce(select(Tomador.nome).where(Tomador.id == Convite.tomador_id).scalar_subquery(),
                          select(Prestador.razao_social).where(Prestador.id == Convite.prestador_id).scalar_subquery())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _nao_encontrado() -> HTTPException:
    return HTTPException(404, NAO_ENCONTRADO)


def criar(session: Session, corpo: NovoConvite, usuario: UsuarioContexto) -> dict:
    if corpo.prestador_id is not None:
        travar_prestador(session, corpo.prestador_id)
    motivo = motivo_recusa_convite(session, usuario, corpo.nivel, corpo.papel, corpo.tomador_id, corpo.prestador_id)
    if motivo is not None:
        raise HTTPException(403, motivo)
    convite = criar_na_transacao(session, corpo.email, corpo.nivel, corpo.papel, corpo.tomador_id,
                                 corpo.prestador_id, usuario.id)
    session.commit()
    return convite


def travar_prestador(session: Session, prestador_id: int) -> None:
    """Serializa, por prestador, a criação de convite e o aceite (que cria o primeiro usuário): a checagem 'prestador
    sem usuário' de escopo.pode_convidar vale até o fim da transação. NO KEY UPDATE não bloqueia as FKs."""
    session.execute(select(Prestador.id).where(Prestador.id == prestador_id).with_for_update(key_share=True)).all()


def criar_na_transacao(session: Session, email: str, nivel: str, papel: str, tomador_id: int | None,
                       prestador_id: int | None, criado_por: int) -> dict:
    """Cria o convite na transação de quem chama (sem checar permissão: isso é de escopo.pode_convidar; o commit
    também é de quem chama)."""
    token = secrets.token_urlsafe(32)
    if tomador_id is not None:
        ativo = session.execute(select(Tomador.ativo).where(Tomador.id == tomador_id)).first()
    elif prestador_id is not None:
        ativo = session.execute(select(Prestador.ativo).where(Prestador.id == prestador_id)).first()
    else:
        ativo = (True,)
    if ativo is None or not ativo[0]:
        raise HTTPException(404, "organização não encontrada ou desativada")
    # Serializa criações para o mesmo e-mail: sem isso, duas requisições simultâneas passariam pela checagem.
    session.execute(select(func.pg_advisory_xact_lock(func.hashtext("convite:" + email))))
    if session.execute(select(1).where(exists().where(func.lower(Usuario.email) == email))).first():
        raise HTTPException(409, "já existe usuário com este e-mail")
    if session.execute(select(1).where(exists().where(
            func.lower(Convite.email) == email, Convite.usado_em.is_(None), Convite.expira_em > func.now()))).first():
        raise HTTPException(409, "já existe convite pendente para este e-mail")
    linha = session.execute(insert(Convite).values(
        token_hash=hash_token(token), email=email, nivel=nivel, papel=papel, tomador_id=tomador_id,
        prestador_id=prestador_id, criado_por=criado_por,
        expira_em=func.now() + timedelta(days=config.CONVITE_VALIDADE_DIAS)
    ).returning(Convite.id, Convite.email, Convite.nivel, Convite.papel, Convite.expira_em)).one()
    return dict(zip(("id", "email", "nivel", "papel", "expira_em"), linha), token=token)


def listar(session: Session, usuario: UsuarioContexto) -> list[dict]:
    """Plataforma: todos. Admin de tomador/prestador: os criados por usuários da própria organização. Membro: 403."""
    onde = filtro_convite_gerenciavel(usuario)
    if onde is None:
        raise HTTPException(403, "apenas administradores listam convites")
    estado = case((Convite.usado_em.is_not(None), "usado"), (Convite.expira_em <= func.now(), "expirado"),
                  else_="pendente")
    linhas = session.execute(
        select(Convite.id, Convite.email, Convite.nivel, Convite.papel, Convite.tomador_id, Convite.prestador_id,
               _NOME_ORG, estado, Convite.criado_por, Convite.criado_em, Convite.expira_em, Convite.usado_em,
               Convite.usuario_id).where(onde).order_by(Convite.id.desc()))
    chaves = ("id", "email", "nivel", "papel", "tomador_id", "prestador_id", "organizacao_nome", "estado",
              "criado_por", "criado_em", "expira_em", "usado_em", "usuario_id")
    return [dict(zip(chaves, l)) for l in linhas]


def revogar(session: Session, usuario: UsuarioContexto, convite_id: int) -> None:
    """Revoga um convite pendente: marca como expirado (`expira_em = now()`), sem apagar a linha. É o mais simples:
    `_UTILIZAVEL`, `prestador_tem_convite_pendente`, o `acesso_prestador` dos contratos e o `estado` da listagem já
    tratam `expira_em <= now()` como convite não pendente, e a linha segue como registro de quem convidou.
    Mesmo escopo da listagem (GET /convites); fora dele, 404. Convite usado: 409. Já expirado/revogado: sem efeito."""
    onde = filtro_convite_gerenciavel(usuario)
    if onde is None:
        raise HTTPException(403, "apenas administradores revogam convites")
    linha = session.execute(select(Convite.usado_em).where(Convite.id == convite_id, onde).with_for_update()).first()
    if linha is None:
        raise HTTPException(404, "convite não encontrado")
    if linha[0] is not None:
        raise HTTPException(409, "convite já usado")
    session.execute(update(Convite).where(Convite.id == convite_id)
                    .values(expira_em=func.least(Convite.expira_em, func.now()))
                    .execution_options(synchronize_session=False))
    session.commit()


def reemitir(session: Session, usuario: UsuarioContexto, convite_id: int) -> dict:
    """Troca o link de um convite NÃO usado: revoga o antigo e cria outro para o mesmo e-mail, nível, papel e
    organização, na mesma transação (se a criação falhar, o antigo continua valendo). Mesmo escopo de
    GET/DELETE /convites (fora dele, 404, igual a inexistente) e a mesma checagem de `motivo_recusa_convite` de
    quem criaria o convite do zero (403). O novo convite herda `criado_por` do original: a regra de aceite que depende
    de quem convidou (cliente convidando prestador) e o escopo de quem o enxerga não mudam por quem reemitiu.
    O token novo só existe nesta resposta."""
    onde = filtro_convite_gerenciavel(usuario)
    if onde is None:
        raise HTTPException(403, "apenas administradores gerenciam convites")
    linha = session.execute(
        select(Convite.email, Convite.nivel, Convite.papel, Convite.tomador_id, Convite.prestador_id,
               Convite.criado_por, Convite.usado_em).where(Convite.id == convite_id, onde)).first()
    if linha is None:
        raise HTTPException(404, "convite não encontrado")
    email, nivel, papel, tomador_id, prestador_id, criado_por, usado_em = linha
    if usado_em is not None:
        raise HTTPException(409, "convite já usado")
    if prestador_id is not None:
        travar_prestador(session, prestador_id)
    motivo = motivo_recusa_convite(session, usuario, nivel, papel, tomador_id, prestador_id)
    if motivo is not None:
        raise HTTPException(403, motivo)
    # Trava a linha e reconfere `usado_em`: um aceite simultâneo não pode ser desfeito pela reemissão.
    if session.execute(select(Convite.usado_em).where(Convite.id == convite_id).with_for_update()).scalar_one()             is not None:
        raise HTTPException(409, "convite já usado")
    session.execute(update(Convite).where(Convite.id == convite_id)
                    .values(expira_em=func.least(Convite.expira_em, func.now()))
                    .execution_options(synchronize_session=False))
    novo = criar_na_transacao(session, email, nivel, papel, tomador_id, prestador_id, criado_por)
    session.commit()
    return novo


def consultar(session: Session, token: str) -> dict:
    if len(token) > TOKEN_MAX:
        raise _nao_encontrado()
    linha = session.execute(
        select(Convite.email, Convite.nivel, _NOME_ORG, Convite.expira_em)
        .where(Convite.token_hash == hash_token(token), *_UTILIZAVEL)).first()
    if linha is None:
        raise _nao_encontrado()
    return dict(zip(("email", "nivel", "organizacao_nome", "expira_em"), linha))


def aceitar(session: Session, token: str, corpo: AceiteIn) -> dict:
    if not config.AUTH_SEGREDO:  # antes de criar o usuário: falha fechada sem deixar conta sem como entrar
        raise HTTPException(503, "autenticação não configurada: defina AUTH_SEGREDO")
    if len(token) > TOKEN_MAX:
        raise _nao_encontrado()
    # Rota pública: confere o convite ANTES do scrypt, para um token falso não custar CPU do servidor.
    # A checagem que vale continua sendo o UPDATE atômico abaixo.
    consultar(session, token)
    session.commit()  # fecha a transação da consulta: nenhuma conexão presa durante o scrypt
    senha_hash = senhas.gerar_hash(corpo.senha)  # fora da transação: o scrypt é lento
    try:  # uma transação: cria o usuário e gasta o convite, ou nada
        criado_por_tomador = exists().where(Usuario.id == Convite.criado_por, Usuario.nivel == "tomador")
        # Atômico: dois aceites simultâneos disputam a mesma linha; o segundo reavalia `usado_em IS NULL` e perde.
        convite = session.execute(
            update(Convite).where(Convite.token_hash == hash_token(token), *_UTILIZAVEL)
            .values(usado_em=func.now())
            .returning(Convite.id, Convite.email, Convite.nivel, Convite.papel, Convite.tomador_id,
                       Convite.prestador_id, criado_por_tomador.correlate(Convite))
            .execution_options(synchronize_session=False)).first()
        if convite is None:
            raise _nao_encontrado()
        id_convite, email, nivel, papel, tomador_id, prestador_id, por_tomador = convite
        if prestador_id is not None:
            travar_prestador(session, prestador_id)  # serializa com a checagem de escopo.pode_convidar
            # Convite de prestador criado por um CLIENTE só serve para o primeiro acesso: se o prestador já tem
            # alguém, a pessoa veria os contratos dele com outros clientes. Recusa sem gastar o convite.
            if por_tomador and prestador_tem_usuario_ativo(session, prestador_id):
                raise _nao_encontrado()
        usuario_id = session.execute(insert(Usuario).values(
            email=email, nome=corpo.nome, senha_hash=senha_hash, nivel=nivel, papel=papel, tomador_id=tomador_id,
            prestador_id=prestador_id).returning(Usuario.id)).scalar_one()
        session.execute(update(Convite).where(Convite.id == id_convite).values(usuario_id=usuario_id)
                        .execution_options(synchronize_session=False))
        session.commit()
    except IntegrityError as e:
        # O e-mail virou usuário depois do convite: a transação voltou e o convite segue pendente.
        session.rollback()
        if not isinstance(e.orig, psycopg.errors.UniqueViolation):
            raise
        raise HTTPException(409, "já existe usuário com o e-mail deste convite")
    return emitir_token(UsuarioContexto(id=usuario_id, email=email, nome=corpo.nome, nivel=nivel, papel=papel,
                                        tomador_id=tomador_id, prestador_id=prestador_id))
