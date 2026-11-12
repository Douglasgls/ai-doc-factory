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

from app import config
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
from app.routers import r

log = logging.getLogger(__name__)
STREAM_TETO_SEGUNDOS = 900  # tempo real máximo (time.monotonic) de uma conexão SSE


def validar_empresa(empresa_id: int | None) -> None:
    if empresa_id is None:
        return
    with psycopg.connect(config.DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM empresa WHERE id = %s", (empresa_id,)).fetchone() is None:
            raise HTTPException(404, f"empresa {empresa_id} não encontrada")


def _reenvio(conn, sha: str, pdf: bytes, empresa_id: int | None) -> tuple[dict, bool]:
    """Mesmo arquivo já enviado: devolve o lote existente e diz se precisa enfileirar a segmentação.
    Lote em 'erro' volta para 'recebido' (reprocessa); 'ocr', 'classificando' e 'concluido' ficam como estão."""
    id_, estado, atual = conn.execute(
        "SELECT id, estado, empresa_id FROM lote WHERE sha256 = %s", (sha,)).fetchone()
    if empresa_id is not None and atual is not None and atual != empresa_id:
        raise HTTPException(409, f"lote {id_} já pertence à empresa {atual}")
    if empresa_id is not None and atual is None:
        conn.execute("UPDATE lote SET empresa_id = %s WHERE id = %s", (empresa_id, id_))
        atual = empresa_id
    reprocessando = False
    if estado == "erro":
        # atômico: de dois reenvios simultâneos, só um enxerga 'erro' e enfileira
        reprocessando = conn.execute(
            "UPDATE lote SET estado = 'recebido' WHERE id = %s AND estado = 'erro' RETURNING id",
            (id_,)).fetchone() is not None
        if reprocessando:
            estado = "recebido"
    # em 'recebido' o enfileirar original pode ter falhado; job duplicado é aceitável (handlers idempotentes)
    reenfileirar = estado == "recebido"
    if reenfileirar:
        original = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
        if not original.is_file():  # a gravação pode ter falhado antes
            original.parent.mkdir(parents=True, exist_ok=True)
            original.write_bytes(pdf)
    resposta = {"lote_id": id_, "estado": estado, "existente": True, "empresa_id": atual}
    if reprocessando:
        resposta["reprocessando"] = True
    return resposta, reenfileirar


def criar_lote(dados: bytes, pdf: bytes, nome_arquivo: str | None, empresa_id: int | None = None) -> dict:
    sha = hashlib.sha256(dados).hexdigest()  # dos bytes originais enviados, PDF ou imagem
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, empresa_id) VALUES (%s, %s, %s) "
            "ON CONFLICT (sha256) DO NOTHING RETURNING id, estado",
            (sha, nome_arquivo or "lote.pdf", empresa_id),
        ).fetchone()
        if row is None:  # mesmo arquivo já enviado
            resposta, reenfileirar = _reenvio(conn, sha, pdf, empresa_id)
        else:
            pasta = Path(config.DATA_DIR) / f"lote_{row[0]}"
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "original.pdf").write_bytes(pdf)
            resposta = {"lote_id": row[0], "estado": row[1], "existente": False, "empresa_id": empresa_id}
            reenfileirar = True
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


def obter_lote(lote_id: int) -> dict:
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute(
            "SELECT id, nome_arquivo, estado, docs_pendentes, empresa_id FROM lote WHERE id = %s", (lote_id,)
        ).fetchone()
        if lote is None:
            raise HTTPException(404, "lote não encontrado")
        docs = conn.execute(
            "SELECT id, ordem, pagina_ini, pagina_fim, estado, tipo, confianca, segmentacao_ambigua, "
            "probabilidades, tipo_original FROM documento WHERE lote_id = %s ORDER BY ordem", (lote_id,)
        ).fetchall()
    ultimo, historico = obter_progresso_lote(lote_id, r)
    return {
        "id": lote[0], "nome_arquivo": lote[1], "estado": lote[2], "docs_pendentes": lote[3], "empresa_id": lote[4],
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


def _ha_pos_processamento_pendente(conn, lote_id: int, docs_pendentes: int = 0) -> bool:
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
    pendente_db = conn.execute(
        "SELECT 1 FROM documento d "
        "LEFT JOIN analise_ponto ap ON ap.documento_id = d.id "
        "WHERE d.lote_id = %s AND ("
        "  d.estado = 'segmentado' "
        "  OR (d.estado = 'classificado' AND d.tipo = 'folha_ponto' "
        "      AND (ap.estado IS NULL OR ap.estado NOT IN ('concluida', 'erro')))"
        ") LIMIT 1",
        (lote_id,),
    ).fetchone()
    return pendente_db is not None


def cancelar_lote(lote_id: int) -> dict:
    """Cancela o processamento de um lote em andamento (inclusive durante extração/análise pós-classificação).
    Só documentos 'segmentado' (ainda não classificados) viram 'erro'; o que já foi classificado ou revisado
    fica como está. Lote em recebido/ocr/classificando vai para 'erro'; lote 'concluido' continua 'concluido'
    e só perde o que faltava de extração/análise. 409 se não há nada a cancelar.
    Ordem de bloqueio igual à do classificador (documentos antes do lote); a flag e a limpeza das tarefas no
    Redis só acontecem depois do commit."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        previo = conn.execute("SELECT estado FROM lote WHERE id = %s", (lote_id,)).fetchone()
        if previo is None:
            raise HTTPException(404, "lote não encontrado")
        if previo[0] != "concluido":
            # 1º bloqueio: linhas de documento (como classificar_documento); um job em voo que já travou o
            # seu documento termina antes; os demais passam a enxergar 'erro' e não fazem fan-in
            conn.execute(
                "UPDATE documento SET estado = 'erro' WHERE lote_id = %s AND estado = 'segmentado'",
                (lote_id,),
            )
        # 2º bloqueio: o lote; serializa dois cliques e relê o estado já com os fan-ins commitados
        lote = conn.execute(
            "SELECT estado, docs_pendentes FROM lote WHERE id = %s FOR UPDATE", (lote_id,)
        ).fetchone()
        if lote is None:
            raise HTTPException(404, "lote não encontrado")
        estado = lote[0]
        if estado == "concluido" and not _ha_pos_processamento_pendente(conn, lote_id, lote[1]):
            raise HTTPException(409, "lote já concluído não pode ser cancelado")
        if estado in ("recebido", "ocr", "classificando"):
            conn.execute("UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s", (lote_id,))
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
    return obter_lote(lote_id)


def reprocessar_lote(lote_id: int) -> dict:
    """Reenfileira um lote em 'erro' a partir do original.pdf salvo em disco.
    Só aceita lotes em estado 'erro' e sem revisões humanas, preservando trabalho já concluído."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute("SELECT id, estado FROM lote WHERE id = %s FOR UPDATE", (lote_id,)).fetchone()
        if lote is None:
            raise HTTPException(404, "lote não encontrado")
        if lote[1] != "erro":
            raise HTTPException(409, f"lote {lote_id} em estado '{lote[1]}' não pode ser reprocessado")
        tem_revisao = conn.execute(
            "SELECT 1 FROM documento WHERE lote_id = %s AND estado = 'revisado' LIMIT 1",
            (lote_id,),
        ).fetchone()
        if tem_revisao is not None:
            raise HTTPException(409, f"lote {lote_id} possui documentos revisados e não pode ser reprocessado")
        original = Path(config.DATA_DIR) / f"lote_{lote_id}" / "original.pdf"
        if not original.is_file():
            raise HTTPException(400, "arquivo original do lote não está disponível para reprocessamento")
        conn.execute("DELETE FROM documento WHERE lote_id = %s", (lote_id,))
        conn.execute(
            "UPDATE lote SET estado = 'recebido', docs_pendentes = 0 WHERE id = %s",
            (lote_id,),
        )
    limpar_cancelado(lote_id, r)
    limpar_tarefas_pos(lote_id, r)
    publicar_evento(
        lote_id,
        "recebido",
        "Reprocessamento iniciado · arquivo na fila...",
        r=r,
    )
    enfileirar(r, config.FILA_SEGMENTAR, {"lote_id": lote_id})
    return obter_lote(lote_id)


def montar_pacote_evento(lote_id: int) -> dict:
    return jsonable_encoder(obter_lote(lote_id))


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
        with psycopg.connect(config.DATABASE_URL) as conn:
            row = conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (lote_id,)).fetchone()
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
