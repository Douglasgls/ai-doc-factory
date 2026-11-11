"""Reenvio do mesmo arquivo: lote em 'erro' reprocessa; os demais estados não mudam.
Contra o Postgres: docker compose exec api python -m pytest tests"""
import uuid
from pathlib import Path

import psycopg
import pytest

from app import config
from app.routers.lotes import actions as lotes_actions

PDF = b"%PDF-1.4 reenvio"


@pytest.fixture
def jobs(monkeypatch):
    enfileirados = []
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda r, fila, payload, *a, **k: enfileirados.append((fila, payload)))
    return enfileirados


@pytest.fixture
def enviar(jobs):
    """Envia bytes únicos; devolve (dados, id do lote). Limpa os lotes no fim."""
    criados = []

    def _enviar():
        dados = PDF + uuid.uuid4().hex.encode()
        id_ = lotes_actions.criar_lote(dados, dados, "a.pdf")["lote_id"]
        criados.append(id_)
        jobs.clear()
        return dados, id_
    yield _enviar
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        for id_ in criados:
            conn.execute("DELETE FROM lote WHERE id = %s", (id_,))


def _estado(id_, novo=None):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        if novo:
            conn.execute("UPDATE lote SET estado = %s WHERE id = %s", (novo, id_))
        return conn.execute("SELECT estado FROM lote WHERE id = %s", (id_,)).fetchone()[0]


def test_lote_em_erro_volta_a_recebido_e_gera_um_job(enviar, jobs):
    dados, id_ = enviar()
    _estado(id_, "erro")
    resp = lotes_actions.criar_lote(dados, dados, "a.pdf")
    assert resp == {"lote_id": id_, "estado": "recebido", "existente": True, "empresa_id": None, "reprocessando": True}
    assert _estado(id_) == "recebido"
    assert jobs == [(config.FILA_SEGMENTAR, {"lote_id": id_})]


@pytest.mark.parametrize("estado", ["ocr", "classificando", "concluido"])
def test_outros_estados_nao_reprocessam(enviar, jobs, estado):
    dados, id_ = enviar()
    _estado(id_, estado)
    resp = lotes_actions.criar_lote(dados, dados, "a.pdf")
    assert resp == {"lote_id": id_, "estado": estado, "existente": True, "empresa_id": None}
    assert _estado(id_) == estado
    assert jobs == []


def test_original_pdf_ausente_e_regravado(enviar, jobs):
    dados, id_ = enviar()
    original = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
    original.unlink()
    _estado(id_, "erro")
    lotes_actions.criar_lote(dados, b"%PDF-novo", "a.pdf")
    assert original.read_bytes() == b"%PDF-novo"
    assert len(jobs) == 1


def test_original_pdf_existente_nao_e_sobrescrito(enviar, jobs):
    dados, id_ = enviar()
    _estado(id_, "erro")
    lotes_actions.criar_lote(dados, b"%PDF-outro", "a.pdf")
    assert (Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf").read_bytes() == dados
