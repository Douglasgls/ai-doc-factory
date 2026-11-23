"""Espera crescente entre tentativas (fila:atrasados), contra o Redis real."""
import json
import threading
import types
import uuid

import pytest
import redis

from app import config, filas
from app.filas import DLQ, enfileirar, liberar_atrasados, processar_um, recuperar_presos


@pytest.fixture
def r(monkeypatch):
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    fila = f"teste_{uuid.uuid4().hex[:8]}"
    relogio = [1000.0]
    monkeypatch.setattr(filas, "time", types.SimpleNamespace(time=lambda: relogio[0]))
    monkeypatch.setattr(config, "ESPERAS_TENTATIVA", (5.0, 30.0, 120.0))
    yield cli, fila, relogio
    cli.delete(fila, f"{fila}:proc", f"{fila}:atrasados")
    for x in cli.lrange(DLQ, 0, -1):
        if json.loads(x)["fila"] == fila:
            cli.lrem(DLQ, 0, x)


def _falha(p):
    raise RuntimeError("falha passageira")


def test_falha_vai_para_atrasados_e_so_volta_depois_do_prazo(r):
    cli, fila, relogio = r
    chamadas = []

    def instavel(p):
        chamadas.append(p)
        if len(chamadas) == 1:
            raise RuntimeError("ConnectError")

    enfileirar(cli, fila, {"lote_id": 1})
    assert processar_um(cli, fila, instavel, timeout=1)
    assert cli.llen(fila) == 0 and cli.llen(f"{fila}:proc") == 0
    assert cli.zcard(f"{fila}:atrasados") == 1
    assert cli.zrange(f"{fila}:atrasados", 0, 0, withscores=True)[0][1] == 1005.0

    relogio[0] = 1004.9  # ainda dentro da espera: não é tentado de novo
    assert processar_um(cli, fila, instavel, timeout=1) is False
    assert len(chamadas) == 1

    relogio[0] = 1005.0  # prazo vencido: libera e sucede
    assert processar_um(cli, fila, instavel, timeout=1)
    assert len(chamadas) == 2
    assert cli.zcard(f"{fila}:atrasados") == 0 and cli.llen(f"{fila}:proc") == 0 and cli.llen(fila) == 0


def test_esperas_crescem_e_tres_falhas_vao_para_dlq(r):
    cli, fila, relogio = r
    enfileirar(cli, fila, {"lote_id": 2})
    prazos = []
    for _ in range(config.MAX_TENTATIVAS):
        assert processar_um(cli, fila, _falha, timeout=1)
        if cli.zcard(f"{fila}:atrasados"):
            prazos.append(cli.zrange(f"{fila}:atrasados", 0, 0, withscores=True)[0][1] - relogio[0])
            relogio[0] += 1000
    assert prazos == [5.0, 30.0]
    assert cli.llen(fila) == 0 and cli.llen(f"{fila}:proc") == 0 and cli.zcard(f"{fila}:atrasados") == 0
    mortos = [json.loads(x) for x in cli.lrange(DLQ, 0, -1) if json.loads(x)["fila"] == fila]
    assert len(mortos) == 1 and mortos[0]["payload"] == {"lote_id": 2}


def test_dois_workers_liberando_juntos_nao_duplicam(r):
    cli, fila, relogio = r
    n = 50
    for i in range(n):
        enfileirar(cli, fila, {"i": i})
        processar_um(cli, fila, _falha, timeout=1)
    assert cli.zcard(f"{fila}:atrasados") == n
    relogio[0] += 10
    barreira = threading.Barrier(2)
    liberados = []

    def worker():
        c = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
        barreira.wait()
        liberados.append(liberar_atrasados(c, fila, agora=relogio[0]))

    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(liberados) == n
    assert cli.llen(fila) == n and cli.zcard(f"{fila}:atrasados") == 0
    assert len({json.loads(x)["payload"]["i"] for x in cli.lrange(fila, 0, -1)}) == n


def test_jobs_identicos_nao_se_fundem_nos_atrasados(r):
    cli, fila, _ = r
    for _ in range(2):
        enfileirar(cli, fila, {"lote_id": 9})
    processar_um(cli, fila, _falha, timeout=1)
    processar_um(cli, fila, _falha, timeout=1)
    assert cli.zcard(f"{fila}:atrasados") == 2


def test_atrasado_nao_e_perdido_por_recuperar_presos(r):
    cli, fila, relogio = r
    enfileirar(cli, fila, {"lote_id": 3})
    processar_um(cli, fila, _falha, timeout=1)
    assert recuperar_presos(cli, fila) == 0  # nada preso em :proc
    assert cli.zcard(f"{fila}:atrasados") == 1  # o atrasado continua guardado
    relogio[0] += 10
    assert liberar_atrasados(cli, fila, agora=relogio[0]) == 1
    assert cli.llen(fila) == 1
