import asyncio
from decimal import Decimal
import hashlib
import json
import logging
import time
from pathlib import Path

import psycopg
from fastapi import HTTPException, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import config
from app.database import SessionLocal
from app.escopo import exigir_contrato_de_upload, filtro_contrato, filtro_lote
from app.eventos import (
    canal_lote,
    limpar_cancelado,
    limpar_tarefas_pos,
    marcar_cancelado,
    obter_progresso_lote,
    publicar_evento,
    tarefas_pos_pendentes,
)
from app.filas import enfileirar
from app.models import AnalisePonto, Contrato, Documento, Lote, Prestador, Tomador
from app.routers import r
from app.routers.auth.actions import UsuarioContexto

log = logging.getLogger(__name__)
STREAM_TETO_SEGUNDOS = 900  # tempo real máximo (time.monotonic) de uma conexão SSE


def validar_contrato(session: Session, contrato_id: int | None, usuario: UsuarioContexto) -> None:
    """Prestador: contrato_id obrigatório (422) e contrato dele ativo (senão 404, sem revelar existência).
    Plataforma: sem contrato_id nada é validado e o lote fica sem contrato
    (lote sem contrato é só da plataforma); com ele, 404 se não existe e 409 se ele, o tomador ou o prestador
    estão inativos."""
    exigir_contrato_de_upload(session, usuario, contrato_id)
    if contrato_id is None:
        return
    linha = session.execute(
        select(Contrato.ativo, Tomador.ativo, Prestador.ativo)
        .join(Tomador, Tomador.id == Contrato.tomador_id).join(Prestador, Prestador.id == Contrato.prestador_id)
        .where(Contrato.id == contrato_id)).first()
    session.commit()  # a validação é uma transação própria, como antes; o upload abre outra
    if linha is None:
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")
    if not all(linha):
        raise HTTPException(409, f"contrato {contrato_id} inativo (ou de tomador/prestador inativo)")


def _lote_tem_revisao(session: Session, lote_id: int) -> bool:
    """True se o lote tem documento 'revisado' (revisão humana que um reprocessamento apagaria)."""
    return session.execute(
        select(1).where(Documento.lote_id == lote_id, Documento.estado == "revisado").limit(1)).first() is not None


def _erro_lote_revisado(lote_id: int) -> HTTPException:
    return HTTPException(409, f"lote {lote_id} possui documentos revisados e não pode ser reprocessado")


def _reenvio(session: Session, sha: str, pdf: bytes, contrato_id: int | None) -> tuple[dict, bool]:
    """Mesmo arquivo já enviado NESTE contrato (ou, sem contrato, já enviado sem contrato): devolve o lote existente
    e diz se precisa enfileirar a segmentação. Lote em 'erro' volta para 'recebido' (reprocessa); 'ocr',
    'classificando' e 'concluido' ficam como estão. O lote nunca troca de contrato.
    Lote em 'erro' com documento revisado não reprocessa (409), para não apagar a revisão humana."""
    id_, estado = session.execute(
        select(Lote.id, Lote.estado).where(Lote.sha256 == sha, Lote.contrato_id.is_not_distinct_from(contrato_id))
    ).one()
    reprocessando = False
    if estado == "erro":
        # atômico: de dois reenvios simultâneos, só um enxerga 'erro' e enfileira
        # (a ausência de documento revisado é checada no mesmo UPDATE, sem janela entre checagem e escrita)
        sem_revisao = ~select(1).where(Documento.lote_id == id_, Documento.estado == "revisado").exists()
        reprocessando = session.execute(
            update(Lote).where(Lote.id == id_, Lote.estado == "erro", sem_revisao).values(estado="recebido")
            .returning(Lote.id).execution_options(synchronize_session=False)).first() is not None
        if reprocessando:
            estado = "recebido"
        elif _lote_tem_revisao(session, id_):
            session.rollback()
            raise _erro_lote_revisado(id_)
    # em 'recebido' o enfileirar original pode ter falhado; job duplicado é aceitável (handlers idempotentes)
    reenfileirar = estado == "recebido"
    if reenfileirar:
        original = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
        if not original.is_file():  # a gravação pode ter falhado antes
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(pdf)
    resposta = {"lote_id": id_, "estado": estado, "existente": True, "contrato_id": contrato_id}
    if reprocessando:
        resposta["reprocessando"] = True
    return resposta, reenfileirar


def criar_lote(session: Session, dados: bytes, pdf: bytes, nome_arquivo: str | None,
               contrato_id: int | None = None) -> dict:
    sha = hashlib.sha256(dados).hexdigest()  # dos bytes originais enviados, PDF ou imagem
    # A unicidade do arquivo é por contrato (dois índices únicos parciais): o ON CONFLICT mira o índice do caso.
    novo = pg_insert(Lote).values(sha256=sha, nome_arquivo=nome_arquivo or "lote.pdf", contrato_id=contrato_id)
    if contrato_id is not None:
        novo = novo.on_conflict_do_nothing(index_elements=[Lote.contrato_id, Lote.sha256],
                                           index_where=Lote.contrato_id.is_not(None))
    else:
        novo = novo.on_conflict_do_nothing(index_elements=[Lote.sha256], index_where=Lote.contrato_id.is_(None))
    try:
        row = session.execute(novo.returning(Lote.id, Lote.estado)).first()
        if row is None:  # mesmo arquivo já enviado neste contrato
            resposta, reenfileirar = _reenvio(session, sha, pdf, contrato_id)
        else:
            pasta = Path(config.DATA_DIR) / f"lote_{row[0]}"
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "original.pdf").write_bytes(pdf)
            resposta = {"lote_id": row[0], "estado": row[1], "existente": False, "contrato_id": contrato_id}
            reenfileirar = True
        session.commit()
    except IntegrityError as e:  # contrato apagado entre a validação e o INSERT
        session.rollback()
        if not isinstance(e.orig, psycopg.errors.ForeignKeyViolation):
            raise
        raise HTTPException(404, f"contrato {contrato_id} não encontrado")
    if reenfileirar:  # só depois do commit, para o worker enxergar o estado novo
        limpar_cancelado(resposta["lote_id"], r)
        limpar_tarefas_pos(resposta["lote_id"], r)
        publicar_evento(
            resposta["lote_id"],
            "recebido",
            "Arquivo recebido na fila de processamento...",
            r=r,
        )
        enfileirar(r, config.FILA_SEGMENTAR, {"lote_id": resposta["lote_id"]})
    return resposta


def _normalizar_probabilidades(probs) -> dict[str, float] | None:
    if not isinstance(probs, dict):
        return None
    return {str(k): float(v) for k, v in probs.items() if isinstance(v, (int, float, Decimal))}


def _json_default(valor):
    if isinstance(valor, Decimal):
        return float(valor)
    return jsonable_encoder(valor)


def _serializar_pacote(pacote: dict, sort_keys: bool = False) -> str:
    return json.dumps(
        jsonable_encoder(pacote),
        sort_keys=sort_keys,
        ensure_ascii=False,
        default=_json_default,
    )


def listar_lotes(session: Session, *, usuario: UsuarioContexto, limite: int = 20, antes_de: int | None = None,
                 estado: str | None = None, contrato_id: int | None = None) -> dict:
    """Resumo dos lotes no escopo do usuário, do mais novo para o mais antigo (uma consulta, com agregação).
    `antes_de` é o cursor por id (id do último item da página anterior). `contrato_id` fora do escopo é 404."""
    if contrato_id is not None and session.execute(
            select(Contrato.id).join(Tomador, Tomador.id == Contrato.tomador_id)
            .join(Prestador, Prestador.id == Contrato.prestador_id)
            .where(Contrato.id == contrato_id, filtro_contrato(usuario))).first() is None:
        raise HTTPException(404, "contrato não encontrado")
    docs = (select(Documento.lote_id.label("lote_id"), func.count().label("total"),
                   func.count().filter(Documento.estado == "em_revisao").label("em_revisao"),
                   func.count().filter(Documento.estado == "erro").label("com_erro"))
            .group_by(Documento.lote_id).subquery())
    consulta = (select(Lote.id, Lote.nome_arquivo, Lote.estado, Lote.docs_pendentes, Lote.contrato_id, Lote.criado_em,
                       func.coalesce(docs.c.total, 0), func.coalesce(docs.c.em_revisao, 0),
                       func.coalesce(docs.c.com_erro, 0))
                .outerjoin(docs, docs.c.lote_id == Lote.id).where(filtro_lote(usuario)))
    if estado is not None:
        consulta = consulta.where(Lote.estado == estado)
    if contrato_id is not None:
        consulta = consulta.where(Lote.contrato_id == contrato_id)
    if antes_de is not None:
        # cursor por id: criado_em é monótono com o id (now() na inserção); a ordem é a mesma de (criado_em, id) DESC
        ref = select(Lote.criado_em).where(Lote.id == antes_de).scalar_subquery()
        consulta = consulta.where(or_(Lote.criado_em < ref, and_(Lote.criado_em == ref, Lote.id < antes_de)))
    linhas = session.execute(consulta.order_by(Lote.criado_em.desc(), Lote.id.desc()).limit(limite + 1)).all()
    pagina = linhas[:limite]
    itens = [{"id": l[0], "nome_arquivo": l[1], "estado": l[2], "docs_pendentes": l[3], "contrato_id": l[4],
              "criado_em": l[5], "total_documentos": l[6], "em_revisao": l[7], "com_erro": l[8]} for l in pagina]
    return {"itens": itens, "proximo_cursor": pagina[-1][0] if len(linhas) > limite else None}


def obter_lote(session: Session, lote_id: int) -> dict:
    lote = session.execute(
        select(Lote.id, Lote.nome_arquivo, Lote.estado, Lote.docs_pendentes, Lote.contrato_id).where(Lote.id == lote_id)
    ).first()
    if lote is None:
        raise HTTPException(404, "lote não encontrado")
    docs = session.execute(
        select(Documento.id, Documento.ordem, Documento.pagina_ini, Documento.pagina_fim, Documento.estado,
               Documento.tipo, Documento.confianca, Documento.segmentacao_ambigua, Documento.probabilidades,
               Documento.tipo_original).where(Documento.lote_id == lote_id).order_by(Documento.ordem)).all()
    ultimo, historico = obter_progresso_lote(lote_id, r)
    return {
        "id": lote[0], "nome_arquivo": lote[1], "estado": lote[2], "docs_pendentes": lote[3], "contrato_id": lote[4],
        "ultimo_evento": ultimo,
        "historico_eventos": historico,
        "documentos": [
            {"id": d[0], "ordem": d[1], "pagina_ini": d[2], "pagina_fim": d[3], "estado": d[4],
             "tipo": d[5], "confianca": float(d[6]) if d[6] is not None else None,
             "segmentacao_ambigua": d[7], "probabilidades": _normalizar_probabilidades(d[8]),
             "tipo_original": d[9]}
            for d in docs
        ],
    }


def caminho_imagem_pagina(lote_id: int, numero: int) -> Path:
    png = Path(config.DATA_DIR) / f"lote_{lote_id}" / f"pag_{numero:04d}.png"
    if not png.is_file():
        raise HTTPException(404, "imagem não encontrada")
    return png


def _ha_pos_processamento_pendente(session: Session, lote_id: int, docs_pendentes: int = 0) -> bool:
    """Verifica o estado real do processamento do lote (Redis + Postgres), identificando se ainda há
    documentos em classificação, extração de campos ou análise de folha de ponto em andamento."""
    if (docs_pendentes or 0) > 0:
        return True
    if tarefas_pos_pendentes(lote_id, r):
        return True
    ultimo, _ = obter_progresso_lote(lote_id, r)
    etapa_atual = (ultimo or {}).get("etapa", "")
    if etapa_atual in ("extracao", "analise_ponto"):
        return True
    pendente_db = session.execute(
        select(1).select_from(Documento).outerjoin(AnalisePonto, AnalisePonto.documento_id == Documento.id)
        .where(Documento.lote_id == lote_id,
               or_(Documento.estado == "segmentado",
                   and_(Documento.estado == "classificado", Documento.tipo == "folha_ponto",
                        or_(AnalisePonto.estado.is_(None), AnalisePonto.estado.not_in(("concluida", "erro"))))))
        .limit(1)).first()
    return pendente_db is not None


def cancelar_lote(session: Session, lote_id: int) -> dict:
    """Cancela o processamento de um lote em andamento (inclusive durante extração/análise pós-classificação).
    Só documentos 'segmentado' (ainda não classificados) viram 'erro'; o que já foi classificado ou revisado
    fica como está. Lote em recebido/ocr/classificando vai para 'erro'; lote 'concluido' continua 'concluido'
    e só perde o que faltava de extração/análise. 409 se não há nada a cancelar.
    Ordem de bloqueio igual à do classificador (documentos antes do lote); a flag e a limpeza das tarefas no
    Redis só acontecem depois do commit."""
    previo = session.execute(select(Lote.estado).where(Lote.id == lote_id)).first()
    if previo is None:
        raise HTTPException(404, "lote não encontrado")
    if previo[0] != "concluido":
        # 1º bloqueio: linhas de documento (como classificar_documento); um job em voo que já travou o
        # seu documento termina antes; os demais passam a enxergar 'erro' e não fazem fan-in
        session.execute(update(Documento).where(Documento.lote_id == lote_id, Documento.estado == "segmentado")
                        .values(estado="erro").execution_options(synchronize_session=False))
    # 2º bloqueio: o lote; serializa dois cliques e relê o estado já com os fan-ins commitados
    lote = session.execute(select(Lote.estado, Lote.docs_pendentes).where(Lote.id == lote_id)
                           .with_for_update()).first()
    if lote is None:
        raise HTTPException(404, "lote não encontrado")
    estado = lote[0]
    if estado == "concluido" and not _ha_pos_processamento_pendente(session, lote_id, lote[1]):
        raise HTTPException(409, "lote já concluído não pode ser cancelado")
    if estado in ("recebido", "ocr", "classificando"):
        session.execute(update(Lote).where(Lote.id == lote_id).values(estado="erro", docs_pendentes=0)
                        .execution_options(synchronize_session=False))
    session.commit()
    # commit feito: só agora o Redis. Falha aqui não pode virar 500, o banco já mudou.
    try:
        marcar_cancelado(lote_id, r)
        limpar_tarefas_pos(lote_id, r)
    except Exception:
        log.exception("lote %s cancelado no banco, mas o Redis falhou (flag/tarefas pendentes)", lote_id)
    if estado == "concluido":  # a classificação terminou; o lote segue concluído e o acompanhamento encerra
        publicar_evento(lote_id, "concluido", "Extração/análise pendente cancelada pelo usuário.", r=r)
    else:
        publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.", r=r)
    return obter_lote(session, lote_id)


def reprocessar_lote(session: Session, lote_id: int) -> dict:
    """Reenfileira um lote em 'erro' a partir do original.pdf salvo em disco.
    Só aceita lotes em estado 'erro' e sem revisões humanas, preservando trabalho já concluído."""
    lote = session.execute(select(Lote.id, Lote.estado).where(Lote.id == lote_id).with_for_update()).first()
    if lote is None:
        raise HTTPException(404, "lote não encontrado")
    if lote[1] != "erro":
        raise HTTPException(409, f"lote {lote_id} em estado '{lote[1]}' não pode ser reprocessado")
    if _lote_tem_revisao(session, lote_id):
        raise _erro_lote_revisado(lote_id)
    original = Path(config.DATA_DIR) / f"lote_{lote_id}" / "original.pdf"
    if not original.is_file():
        raise HTTPException(400, "arquivo original do lote não está disponível para reprocessamento")
    session.execute(delete(Documento).where(Documento.lote_id == lote_id).execution_options(synchronize_session=False))
    session.execute(update(Lote).where(Lote.id == lote_id).values(estado="recebido", docs_pendentes=0)
                    .execution_options(synchronize_session=False))
    session.commit()
    limpar_cancelado(lote_id, r)
    limpar_tarefas_pos(lote_id, r)
    publicar_evento(
        lote_id,
        "recebido",
        "Reprocessamento iniciado · arquivo na fila...",
        r=r,
    )
    enfileirar(r, config.FILA_SEGMENTAR, {"lote_id": lote_id})
    return obter_lote(session, lote_id)


def montar_pacote_evento(lote_id: int) -> dict:
    # Sessão própria e curta: o stream SSE roda em threads fora do ciclo da requisição (Depends(get_session))
    # e não pode segurar uma conexão do banco enquanto espera mensagens.
    with SessionLocal() as session:
        return jsonable_encoder(obter_lote(session, lote_id))


def _motivo_termino(lote_id: int, estado: str, docs_pendentes: int | None) -> str | None:
    """Motivo de encerrar o stream, só com fatos verificáveis: estado do lote no banco e tarefas pós pendentes.
    'erro' encerra sempre; 'concluido' só encerra sem documentos pendentes nem tarefas pós registradas
    (a ordem importa: o banco é lido antes do Redis, e o classificador registra a tarefa antes do commit)."""
    if estado == "erro":
        return "erro"
    if estado != "concluido" or (docs_pendentes or 0) > 0:
        return None
    if tarefas_pos_pendentes(lote_id, r):
        return None
    return "finalizado"


def _lote_totalmente_finalizado(lote_id: int, pacote: dict) -> bool:
    return _motivo_termino(lote_id, pacote["estado"], pacote.get("docs_pendentes")) is not None


def _tick_stream(lote_id: int, reconstruir: bool) -> tuple[dict | None, str | None]:
    """Todo o I/O (Postgres e Redis) de uma iteração do stream, para rodar em uma única chamada de thread.
    Devolve (pacote, motivo): o pacote completo só é montado se `reconstruir` ou se o stream vai encerrar;
    caso contrário é None. `motivo` é None enquanto o stream deve continuar."""
    if not reconstruir:
        with SessionLocal() as session:
            row = session.execute(select(Lote.estado, Lote.docs_pendentes).where(Lote.id == lote_id)).first()
        if row is None:
            return montar_pacote_ausente(lote_id), "erro"
        motivo = _motivo_termino(lote_id, row[0], row[1])
        if motivo is None:
            return None, None
    try:
        pacote = montar_pacote_evento(lote_id)
    except HTTPException:  # lote apagado durante o stream
        return montar_pacote_ausente(lote_id), "erro"
    return pacote, _motivo_termino(lote_id, pacote["estado"], pacote.get("docs_pendentes"))


def montar_pacote_ausente(lote_id: int) -> dict:
    return {"id": lote_id, "estado": "erro", "docs_pendentes": 0, "ultimo_evento": None,
            "historico_eventos": [], "documentos": []}


def _frame(pacote: dict, motivo: str | None = None) -> str:
    """Frame SSE `data: {json}`; no pacote final acrescenta os campos aditivos `fim` e `motivo`."""
    if motivo is not None:
        pacote = {**pacote, "fim": True, "motivo": motivo}
    return f"data: {_serializar_pacote(pacote)}\n\n"


async def stream_eventos_lote(lote_id: int, request: Request, once: bool = False):
    """Gerador assíncrono SSE (Server-Sent Events) alimentado por Redis Pub/Sub.
    Todo o I/O (banco e Redis) de cada iteração roda em thread (asyncio.to_thread), sem bloquear o event loop.
    O último pacote traz `"fim": true` e `"motivo"` (finalizado | erro | tempo_esgotado)."""
    pubsub = None
    if not once:
        try:
            if hasattr(r, "pubsub"):
                pubsub = r.pubsub(ignore_subscribe_messages=True)
                await asyncio.to_thread(pubsub.subscribe, canal_lote(lote_id))
        except Exception:
            pubsub = None

    inicio = time.monotonic()
    try:
        pacote, motivo = await asyncio.to_thread(_tick_stream, lote_id, True)
        ultimo_json = _serializar_pacote(pacote, sort_keys=True)
        yield _frame(pacote, motivo)

        if once or motivo is not None or pubsub is None:
            return

        ticks_sem_consulta = 0
        while True:
            if await request.is_disconnected():
                break
            if time.monotonic() - inicio >= STREAM_TETO_SEGUNDOS:
                pacote, motivo = await asyncio.to_thread(_tick_stream, lote_id, True)
                yield _frame(pacote, motivo or "tempo_esgotado")
                break
            msg = await asyncio.to_thread(pubsub.get_message, True, 1.0)
            if msg is not None:
                # Drena mensagens acumuladas no mesmo instante para fazer apenas 1 leitura no banco
                while await asyncio.to_thread(pubsub.get_message, True, 0.0) is not None:
                    pass
                ticks_sem_consulta = 0
                reconstruir = True
            else:
                ticks_sem_consulta += 1
                reconstruir = ticks_sem_consulta >= 15
                if reconstruir:
                    ticks_sem_consulta = 0
            pacote, motivo = await asyncio.to_thread(_tick_stream, lote_id, reconstruir)
            if motivo is not None:
                yield _frame(pacote, motivo)
                break
            if pacote is None:
                yield ": keepalive\n\n"
                continue
            atual_json = _serializar_pacote(pacote, sort_keys=True)
            if msg is not None or atual_json != ultimo_json:
                ultimo_json = atual_json
                yield _frame(pacote)
            else:
                yield ": keepalive\n\n"
    finally:
        if pubsub is not None:
            try:
                await asyncio.to_thread(pubsub.close)
            except Exception:
                pass
