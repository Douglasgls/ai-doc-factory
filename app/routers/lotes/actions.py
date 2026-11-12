import asyncio
import hashlib
import json
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
             "segmentacao_ambigua": d[7], "probabilidades": d[8], "tipo_original": d[9]}
            for d in docs
        ],
    }


def caminho_imagem_pagina(lote_id: int, numero: int) -> Path:
    png = Path(config.DATA_DIR) / f"lote_{lote_id}" / f"pag_{numero:04d}.png"
    if not png.is_file():
        raise HTTPException(404, "imagem não encontrada")
    return png


def cancelar_lote(lote_id: int) -> dict:
    """Cancela o processamento de um lote em andamento, marcando-o como 'erro' e sinalizando aos workers.
    Rejeita com 409 se o lote já estiver concluído (para não bloquear extração/análise em lote concluído)."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute("SELECT id, estado FROM lote WHERE id = %s FOR UPDATE", (lote_id,)).fetchone()
        if lote is None:
            raise HTTPException(404, "lote não encontrado")
        if lote[1] == "concluido":
            raise HTTPException(409, "lote já concluído não pode ser cancelado")
        marcar_cancelado(lote_id, r)
        limpar_tarefas_pos(lote_id, r)
        if lote[1] in ("recebido", "ocr", "classificando"):
            conn.execute(
                "UPDATE documento SET estado = 'erro' WHERE lote_id = %s AND estado = 'segmentado'",
                (lote_id,),
            )
            conn.execute(
                "UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s",
                (lote_id,),
            )
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


def _lote_totalmente_finalizado(lote_id: int, pacote: dict) -> bool:
    """Retorna True se o lote chegou a um estado terminal (erro ou concluído sem tarefas pós-classificação pendentes)."""
    if pacote["estado"] == "erro":
        return True
    if pacote["estado"] != "concluido":
        return False
    if (pacote.get("docs_pendentes") or 0) > 0:
        return False
    if tarefas_pos_pendentes(lote_id, r):
        return False
    etapa_atual = (pacote.get("ultimo_evento") or {}).get("etapa", "")
    return etapa_atual in ("concluido", "")


async def stream_eventos_lote(lote_id: int, request: Request, once: bool = False):
    """Gerador assíncrono SSE (Server-Sent Events) alimentado por Redis Pub/Sub.
    Todas as consultas ao banco rodam em thread pool (asyncio.to_thread) e apenas quando chega evento
    no Redis Pub/Sub (ou a cada 15s como fallback), evitando bloquear o event loop com abas abertas."""
    pubsub = None
    if not once:
        try:
            if hasattr(r, "pubsub"):
                pubsub = r.pubsub(ignore_subscribe_messages=True)
                await asyncio.to_thread(pubsub.subscribe, canal_lote(lote_id))
        except Exception:
            pubsub = None

    try:
        pacote = await asyncio.to_thread(montar_pacote_evento, lote_id)
        ultimo_json = json.dumps(pacote, sort_keys=True, ensure_ascii=False)
        yield f"data: {json.dumps(pacote, ensure_ascii=False)}\n\n"

        if once or _lote_totalmente_finalizado(lote_id, pacote) or pubsub is None:
            return

        ticks_sem_consulta = 0
        for _ in range(900):  # teto de 15 minutos
            if await request.is_disconnected():
                break
            msg = await asyncio.to_thread(pubsub.get_message, True, 1.0)
            if msg is not None:
                # Drena mensagens acumuladas no mesmo instante para fazer apenas 1 leitura no banco
                while await asyncio.to_thread(pubsub.get_message, True, 0.0) is not None:
                    pass
                ticks_sem_consulta = 0
                pacote = await asyncio.to_thread(montar_pacote_evento, lote_id)
                atual_json = json.dumps(pacote, sort_keys=True, ensure_ascii=False)
                ultimo_json = atual_json
                yield f"data: {json.dumps(pacote, ensure_ascii=False)}\n\n"
            else:
                ticks_sem_consulta += 1
                if ticks_sem_consulta >= 15:
                    ticks_sem_consulta = 0
                    pacote = await asyncio.to_thread(montar_pacote_evento, lote_id)
                    atual_json = json.dumps(pacote, sort_keys=True, ensure_ascii=False)
                    if atual_json != ultimo_json:
                        ultimo_json = atual_json
                        yield f"data: {json.dumps(pacote, ensure_ascii=False)}\n\n"
                    else:
                        yield ": keepalive\n\n"
                else:
                    yield ": keepalive\n\n"

            if _lote_totalmente_finalizado(lote_id, pacote):
                break
    finally:
        if pubsub is not None:
            try:
                await asyncio.to_thread(pubsub.close)
            except Exception:
                pass
