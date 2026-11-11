"""Jobs ilegíveis vão direto para a dlq, sem derrubar o worker."""
import json
import uuid

import pytest
import redis

from app import config
from app.filas import DLQ, enfileirar, processar_um


@pytest.fixture
def r():
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    fila = f"teste_{uuid.uuid4().hex[:8]}"
    yield cli, fila
    cli.delete(fila, f"{fila}:proc")
    for x in cli.lrange(DLQ, 0, -1):
        try:
            if json.loads(x).get("fila") == fila:
                cli.lrem(DLQ, 0, x)
        except ValueError:
            pass


def _mortos(cli, fila):
    return [json.loads(x) for x in cli.lrange(DLQ, 0, -1) if json.loads(x).get("fila") == fila]


@pytest.mark.parametrize("bruto", ["{nao e json", "[1, 2]", "42", '{"outra": 1}'])
def test_job_ilegivel_vai_para_dlq(r, bruto):
    cli, fila = r
    chamadas = []
    cli.lpush(fila, bruto)
    assert processar_um(cli, fila, chamadas.append, timeout=1) is True
    assert chamadas == []
    assert cli.llen(fila) == 0 and cli.llen(f"{fila}:proc") == 0
    mortos = _mortos(cli, fila)
    assert len(mortos) == 1 and mortos[0]["bruto"] == bruto and mortos[0]["invalido"] is True


def test_sem_tentativas_conta_como_zero(r):
    cli, fila = r
    cli.lpush(fila, json.dumps({"payload": {"lote_id": 3}}))

    def falha(p):
        raise RuntimeError("boom")

    assert processar_um(cli, fila, falha, timeout=1) is True
    # primeira falha: volta para a fila com tentativas=1
    assert json.loads(cli.lrange(fila, 0, -1)[0])["tentativas"] == 1
    assert cli.llen(f"{fila}:proc") == 0


def test_job_valido_seguinte_ainda_e_processado(r):
    cli, fila = r
    recebidos = []
    enfileirar(cli, fila, {"lote_id": 9})  # lpush: consumido por último
    cli.rpush(fila, "lixo{")  # consumido primeiro (BLMOVE pela direita)
    assert processar_um(cli, fila, recebidos.append, timeout=1)
    assert recebidos == []
    assert processar_um(cli, fila, recebidos.append, timeout=1)
    assert recebidos == [{"lote_id": 9}]
