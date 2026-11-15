"""Falha definitiva, fan-in e segmentação com LLM. Contra o Postgres/Redis do compose."""
import json
import uuid

import httpx
import psycopg
import pytest
import redis

from app import classificar, config, llm, ocr, segmentacao
from app.filas import DLQ, enfileirar, processar_um

HOLERITE = "HOLERITE proventos descontos liquido a receber Ana Silva"


def _criar_lote(textos):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        id_ = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 't.pdf', 'ocr') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        for n, t in enumerate(textos, 1):
            conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, %s, %s)", (id_, n, t))
    return id_


def _apagar_lote(id_):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (id_,))


@pytest.fixture
def lote():
    id_ = _criar_lote([HOLERITE + " Página 1 de 1", "ATESTADO MÉDICO CID afastamento Página 1 de 1"])
    yield id_
    _apagar_lote(id_)


@pytest.fixture
def lote_ambiguo(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.0)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 1.1)  # tudo cai na faixa ambígua
    monkeypatch.setattr(segmentacao.config, "SEG_RESIDUAL_MAX_ALNUM", 0)  # páginas de teste são curtas: sem regra residual
    id_ = _criar_lote([HOLERITE, HOLERITE + " continuação"])
    yield id_
    _apagar_lote(id_)


@pytest.fixture
def r():
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    fila = f"teste_{uuid.uuid4().hex[:8]}"
    yield cli, fila
    cli.delete(fila, f"{fila}:proc")
    for x in cli.lrange(DLQ, 0, -1):
        if json.loads(x)["fila"] == fila:
            cli.lrem(DLQ, 0, x)


def _estado(lote_id):
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (lote_id,)).fetchone()
        docs = conn.execute("SELECT estado FROM documento WHERE lote_id = %s ORDER BY ordem", (lote_id,)).fetchall()
    return lote, [d[0] for d in docs]


def test_ao_esgotar_marca_erro_faz_fan_in_sem_decremento_duplo(lote):
    a, b = ocr.segmentar_e_gravar(lote)
    classificar.marcar_erro({"documento_id": a})
    classificar.marcar_erro({"documento_id": a})  # repetido: não decrementa de novo
    assert _estado(lote) == (("classificando", 1), ["erro", "segmentado"])
    classificar.classificar_documento({"documento_id": b})
    assert _estado(lote)[0] == ("concluido", 0)
    classificar.marcar_erro({"documento_id": b})  # já decidido: não sobrescreve
    assert _estado(lote)[1][1] != "erro"


def test_jev_falha_de_vez_vai_para_dlq_e_documento_fica_em_erro(lote, r, monkeypatch):
    cli, fila = r
    a, b = ocr.segmentar_e_gravar(lote)
    monkeypatch.setattr(config, "CLASSIFICADOR", "jev")  # rede bloqueada pela conftest => LLMErro
    enfileirar(cli, fila, {"documento_id": a})
    for _ in range(config.MAX_TENTATIVAS):
        processar_um(cli, fila, classificar.classificar_documento, timeout=1, ao_esgotar=classificar.marcar_erro)
    mortos = [json.loads(x)["payload"] for x in cli.lrange(DLQ, 0, -1) if json.loads(x)["fila"] == fila]
    assert mortos == [{"documento_id": a}]
    assert _estado(lote) == (("classificando", 1), ["erro", "segmentado"])
    monkeypatch.setattr(config, "CLASSIFICADOR", "regras")
    classificar.classificar_documento({"documento_id": b})
    assert _estado(lote)[0] == ("concluido", 0)


def test_callback_ausente_nada_muda_e_callback_que_falha_nao_perde_o_job(r):
    cli, fila = r

    def falha(_):
        raise RuntimeError("x")
    for cb in (None, falha):
        enfileirar(cli, fila, {"documento_id": 1}, tentativas=config.MAX_TENTATIVAS - 1)
        processar_um(cli, fila, falha, timeout=1, ao_esgotar=cb)
        assert cli.llen(f"{fila}:proc") == 0
    assert sum(json.loads(x)["fila"] == fila for x in cli.lrange(DLQ, 0, -1)) == 2


def test_falha_do_llm_na_segmentacao_nao_derruba_o_lote(lote_ambiguo):
    ids = ocr.segmentar_e_gravar(lote_ambiguo)  # rede bloqueada: o Jev "cai", o lote segue
    assert len(ids) == 2
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT segmentacao_ambigua FROM documento WHERE id = %s", (ids[1],)).fetchone()[0]


def test_chamada_noul_acontece_fora_da_transacao(lote_ambiguo, monkeypatch):
    """Durante a chamada de rede, outra conexão consegue o FOR UPDATE do lote (não há lock preso)."""
    monkeypatch.setattr(config, "CLASSIFICADOR", "jev")  # em modo regras a pergunta nem sai
    visto = []

    def enviar(url, headers, corpo):
        with psycopg.connect(config.DATABASE_URL) as outra:
            try:
                outra.execute("SELECT 1 FROM lote WHERE id = %s FOR UPDATE NOWAIT", (lote_ambiguo,))
                visto.append("livre")
            except psycopg.errors.LockNotAvailable:
                visto.append("travado")
        return httpx.Response(200, json={"answers": {"q": {"type": "noul", "noul": 0.9}}})
    monkeypatch.setattr(llm, "_enviar", enviar)
    assert len(ocr.segmentar_e_gravar(lote_ambiguo)) == 1  # LLM disse "mesmo documento"
    assert visto == ["livre"]
