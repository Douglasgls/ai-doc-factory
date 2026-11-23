"""Filas Redis com ack: BLMOVE fila -> fila:proc, retry 3x, depois dlq."""
import json
import logging
import time
import uuid
from typing import Callable

import redis

from app import config
from app.config import MAX_TENTATIVAS

log = logging.getLogger(__name__)
DLQ = "dlq"


# Falha -> atrasados: tira de :proc e põe no ZSET em um único passo atômico (nunca perde nem duplica).
_LUA_ATRASAR = """
local removidos = redis.call('LREM', KEYS[1], 1, ARGV[1])
if removidos == 1 then
  redis.call('ZADD', KEYS[2], ARGV[3], ARGV[2])
end
return removidos
"""
# Libera os vencidos: ZREM só conta para quem de fato removeu, então dois workers nunca liberam o mesmo job.
_LUA_LIBERAR = """
local vencidos = redis.call('ZRANGE', KEYS[1], '-inf', ARGV[1], 'BYSCORE', 'LIMIT', 0, 100)
local n = 0
for _, job in ipairs(vencidos) do
  if redis.call('ZREM', KEYS[1], job) == 1 then
    redis.call('LPUSH', KEYS[2], job)
    n = n + 1
  end
end
return n
"""


def _espera(tentativas: int) -> float:
    esperas = config.ESPERAS_TENTATIVA
    return esperas[min(tentativas, len(esperas)) - 1] if esperas else 0.0


def liberar_atrasados(r: redis.Redis, fila: str, agora: float | None = None) -> int:
    """Move para a fila os jobs de fila:atrasados cujo prazo já venceu. Atômico e seguro com vários workers."""
    agora = time.time() if agora is None else agora
    return int(r.eval(_LUA_LIBERAR, 2, f"{fila}:atrasados", fila, agora))


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
    liberar_atrasados(r, fila)
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
        morto = job["tentativas"] >= MAX_TENTATIVAS
        log.exception("job falhou (tentativa %s/%s) -> %s", job["tentativas"], MAX_TENTATIVAS,
                      DLQ if morto else "atrasados")
        if morto:
            # reenfileira antes de remover de :proc, para nunca perder o job
            r.lpush(DLQ, json.dumps(job))
            if ao_esgotar is not None:
                try:
                    ao_esgotar(job["payload"])
                except Exception:
                    log.exception("ao_esgotar falhou; o job permanece na dlq")
        else:
            # espera crescente; sai de :proc e entra em atrasados de forma atômica (já faz o ack)
            # uid evita que dois jobs idênticos virem o mesmo membro do ZSET (e um deles se perca)
            job["uid"] = uuid.uuid4().hex
            removidos = r.eval(_LUA_ATRASAR, 2, proc, f"{fila}:atrasados", bruto, json.dumps(job),
                               time.time() + _espera(job["tentativas"]))
            if not removidos:
                # outra réplica já recuperou este job de :proc: a cópia da fila é a válida, não cria outra
                log.warning("job de %s não estava mais em :proc (já recuperado); não atrasa de novo", fila)
            return True
    r.lrem(proc, 1, bruto)
    return True


def rodar_worker(r: redis.Redis, fila: str, handler: Callable[[dict], None],
                 ao_esgotar: Callable[[dict], None] | None = None) -> None:
    n = recuperar_presos(r, fila)
    log.info("worker ouvindo %s (%s jobs recuperados de %s:proc)", fila, n, fila)
    while True:
        processar_um(r, fila, handler, timeout=1, ao_esgotar=ao_esgotar)
