"""Testes reais contra o Redis do compose: docker compose exec api python -m pytest tests"""
import json
import uuid

import pytest
import redis

from app import config
from app.filas import DLQ, enfileirar, processar_um, recuperar_presos


@pytest.fixture
def r():
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    fila = f"teste_{uuid.uuid4().hex[:8]}"
    yield cli, fila
    cli.delete(fila, f"{fila}:proc", f"{fila}:atrasados")
    for x in cli.lrange(DLQ, 0, -1):  # remove só os mortos desta fila de teste
        if json.loads(x)["fila"] == fila:
            cli.lrem(DLQ, 0, x)


def test_sucesso_faz_ack(r):
    cli, fila = r
    recebidos = []
    enfileirar(cli, fila, {"lote_id": 1})
    assert processar_um(cli, fila, recebidos.append, timeout=1)
    assert recebidos == [{"lote_id": 1}]
    assert cli.llen(fila) == 0 and cli.llen(f"{fila}:proc") == 0


def test_fila_vazia(r):
    cli, fila = r
    assert processar_um(cli, fila, lambda p: None, timeout=1) is False


def test_retry_3x_e_depois_dlq(r):
    cli, fila = r
    chamadas = []

    def falha(p):
        chamadas.append(p)
        raise RuntimeError("boom")

    enfileirar(cli, fila, {"lote_id": 2})
    while processar_um(cli, fila, falha, timeout=1):
        pass
    assert len(chamadas) == config.MAX_TENTATIVAS
    assert cli.llen(fila) == 0 and cli.llen(f"{fila}:proc") == 0
    mortos = [json.loads(x) for x in cli.lrange(DLQ, 0, -1) if json.loads(x)["fila"] == fila]
    assert len(mortos) == 1 and mortos[0]["payload"] == {"lote_id": 2}


def test_recupera_presos_ao_subir(r):
    cli, fila = r
    enfileirar(cli, fila, {"documento_id": 7})
    # simula worker que morreu depois do BLMOVE e antes do ack
    cli.blmove(fila, f"{fila}:proc", 1, "RIGHT", "LEFT")
    assert cli.llen(f"{fila}:proc") == 1 and cli.llen(fila) == 0
    assert recuperar_presos(cli, fila) == 1
    recebidos = []
    assert processar_um(cli, fila, recebidos.append, timeout=1)
    assert recebidos == [{"documento_id": 7}]
