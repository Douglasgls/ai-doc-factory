"""Publicação e leitura de eventos de progresso em tempo real via Redis Pub/Sub (SSE)."""
import json
import logging
from datetime import datetime, timezone

import redis

from app import config

log = logging.getLogger(__name__)

TTL_EVENTOS = 3600
MAX_HISTORICO = 50


def canal_lote(lote_id: int) -> str:
    return f"eventos:lote:{lote_id}"


def _chave_progresso(lote_id: int) -> str:
    return f"progresso:lote:{lote_id}"


def _chave_historico(lote_id: int) -> str:
    return f"historico:lote:{lote_id}"


def _chave_cancelado(lote_id: int) -> str:
    return f"cancelado:lote:{lote_id}"


def _cliente(r: redis.Redis | None = None) -> redis.Redis:
    return r or redis.Redis.from_url(config.REDIS_URL, decode_responses=True)


def publicar_evento(
    lote_id: int,
    etapa: str,
    mensagem: str,
    r: redis.Redis | None = None,
    **extras,
) -> dict:
    """Publica um evento de progresso no canal do lote e salva o último estado no Redis.
    Nunca levanta exceção para não interromper o processamento dos workers."""
    evento = {
        "lote_id": lote_id,
        "etapa": etapa,
        "mensagem": mensagem,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **extras,
    }
    try:
        cli = _cliente(r)
        payload = json.dumps(evento, ensure_ascii=False)
        cli.set(_chave_progresso(lote_id), payload, ex=TTL_EVENTOS)
        if hasattr(cli, "rpush"):
            cli.rpush(_chave_historico(lote_id), payload)
            if hasattr(cli, "ltrim"):
                cli.ltrim(_chave_historico(lote_id), -MAX_HISTORICO, -1)
            if hasattr(cli, "expire"):
                cli.expire(_chave_historico(lote_id), TTL_EVENTOS)
        if hasattr(cli, "publish"):
            cli.publish(canal_lote(lote_id), payload)
    except Exception:
        log.debug("não foi possível publicar evento SSE do lote %s", lote_id)
    return evento


def obter_progresso_lote(lote_id: int, r: redis.Redis | None = None) -> tuple[dict | None, list[dict]]:
    """Retorna (ultimo_evento, historico_eventos) armazenados no Redis para o lote."""
    ultimo = None
    historico: list[dict] = []
    try:
        cli = _cliente(r)
        raw_ultimo = cli.get(_chave_progresso(lote_id)) if hasattr(cli, "get") else None
        if raw_ultimo:
            ultimo = json.loads(raw_ultimo)
        if hasattr(cli, "lrange"):
            itens = cli.lrange(_chave_historico(lote_id), 0, -1) or []
            historico = [json.loads(i) for i in itens if i]
    except Exception:
        log.debug("não foi possível ler progresso do lote %s no Redis", lote_id)
    return ultimo, historico


def marcar_cancelado(lote_id: int, r: redis.Redis | None = None) -> None:
    try:
        cli = _cliente(r)
        cli.set(_chave_cancelado(lote_id), "1", ex=TTL_EVENTOS)
    except Exception:
        log.debug("não foi possível marcar lote %s como cancelado no Redis", lote_id)


def limpar_cancelado(lote_id: int, r: redis.Redis | None = None) -> None:
    try:
        cli = _cliente(r)
        if hasattr(cli, "delete"):
            cli.delete(_chave_cancelado(lote_id))
    except Exception:
        log.debug("não foi possível limpar flag de cancelamento do lote %s", lote_id)


def lote_cancelado(lote_id: int, r: redis.Redis | None = None) -> bool:
    try:
        cli = _cliente(r)
        return bool(cli.get(_chave_cancelado(lote_id))) if hasattr(cli, "get") else False
    except Exception:
        return False

