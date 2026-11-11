"""Filas Redis com ack: BLMOVE fila -> fila:proc, retry 3x, depois dlq."""
import json
import logging
from typing import Callable

import redis

from app.config import MAX_TENTATIVAS

log = logging.getLogger(__name__)
DLQ = "dlq"


def enfileirar(r: redis.Redis, fila: str, payload: dict, tentativas: int = 0) -> None:
    r.lpush(fila, json.dumps({"payload": payload, "tentativas": tentativas, "fila": fila}))


def recuperar_presos(r: redis.Redis, fila: str) -> int:
    """Devolve para a fila os jobs presos em fila:proc (chamar ao subir o worker)."""
    n = 0
    while r.lmove(f"{fila}:proc", fila, "LEFT", "RIGHT"):
        n += 1
    return n


def processar_um(r: redis.Redis, fila: str, handler: Callable[[dict], None], timeout: int = 5,
                 ao_esgotar: Callable[[dict], None] | None = None) -> bool:
    """Consome um job. Ack (remoção de :proc) só após sucesso. Retorna False se a fila estava vazia.
    ao_esgotar(payload), opcional, roda depois que o job foi para a dlq; se falhar, o job segue na dlq."""
    proc = f"{fila}:proc"
    bruto = r.blmove(fila, proc, timeout, "RIGHT", "LEFT")
    if bruto is None:
        return False
    try:
        job = json.loads(bruto)
        if not isinstance(job, dict) or "payload" not in job:
            raise ValueError("job não é um objeto com 'payload'")
        job["tentativas"] = int(job.get("tentativas", 0))
    except (ValueError, TypeError) as e:
        # job ilegível: dlq direta (conteúdo bruto preservado), sem derrubar o worker nem voltar à fila
        log.error("job inválido em %s (%s) -> dlq", fila, e)
        r.lpush(DLQ, json.dumps({"fila": fila, "invalido": True, "erro": str(e), "bruto": str(bruto)}))
        r.lrem(proc, 1, bruto)
        return True
    try:
        handler(job["payload"])
    except Exception:
        job["tentativas"] += 1
        destino = DLQ if job["tentativas"] >= MAX_TENTATIVAS else fila
        log.exception("job falhou (tentativa %s/%s) -> %s", job["tentativas"], MAX_TENTATIVAS, destino)
        # reenfileira antes de remover de :proc, para nunca perder o job
        r.lpush(destino, json.dumps(job))
        if destino == DLQ and ao_esgotar is not None:
            try:
                ao_esgotar(job["payload"])
            except Exception:
                log.exception("ao_esgotar falhou; o job permanece na dlq")
    r.lrem(proc, 1, bruto)
    return True


def rodar_worker(r: redis.Redis, fila: str, handler: Callable[[dict], None],
                 ao_esgotar: Callable[[dict], None] | None = None) -> None:
    n = recuperar_presos(r, fila)
    log.info("worker ouvindo %s (%s jobs recuperados de %s:proc)", fila, n, fila)
    while True:
        processar_um(r, fila, handler, ao_esgotar=ao_esgotar)
