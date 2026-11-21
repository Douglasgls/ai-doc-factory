"""Reenvio do mesmo arquivo: lote em 'erro' reprocessa; os demais estados não mudam.
Contra o Postgres: docker compose exec api python -m pytest tests"""
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi import HTTPException

from app import config, ocr
from app.routers.lotes import actions as lotes_actions

PDF = b"%PDF-1.4 reenvio"


@pytest.fixture
def jobs(monkeypatch):
    enfileirados = []
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda r, fila, payload, *a, **k: enfileirados.append((fila, payload)))
    return enfileirados


@pytest.fixture
def enviar(jobs, sessao):
    """Envia bytes únicos; devolve (dados, id do lote). Limpa os lotes no fim."""
    criados = []

    def _enviar():
        dados = PDF + uuid.uuid4().hex.encode()
        id_ = lotes_actions.criar_lote(sessao, dados, dados, "a.pdf")["lote_id"]
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


def test_lote_em_erro_volta_a_recebido_e_gera_um_job(enviar, jobs, sessao):
    dados, id_ = enviar()
    _estado(id_, "erro")
    resp = lotes_actions.criar_lote(sessao, dados, dados, "a.pdf")
    assert resp == {"lote_id": id_, "estado": "recebido", "existente": True, "contrato_id": None, "reprocessando": True}
    assert _estado(id_) == "recebido"
    assert jobs == [(config.FILA_SEGMENTAR, {"lote_id": id_})]


@pytest.mark.parametrize("estado", ["ocr", "classificando", "concluido"])
def test_outros_estados_nao_reprocessam(enviar, jobs, estado, sessao):
    dados, id_ = enviar()
    _estado(id_, estado)
    resp = lotes_actions.criar_lote(sessao, dados, dados, "a.pdf")
    assert resp == {"lote_id": id_, "estado": estado, "existente": True, "contrato_id": None}
    assert _estado(id_) == estado
    assert jobs == []


def test_original_pdf_ausente_e_regravado(enviar, jobs, sessao):
    dados, id_ = enviar()
    original = Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf"
    original.unlink()
    _estado(id_, "erro")
    lotes_actions.criar_lote(sessao, dados, b"%PDF-novo", "a.pdf")
    assert original.read_bytes() == b"%PDF-novo"
    assert len(jobs) == 1


def test_original_pdf_existente_nao_e_sobrescrito(enviar, jobs, sessao):
    dados, id_ = enviar()
    _estado(id_, "erro")
    lotes_actions.criar_lote(sessao, dados, b"%PDF-outro", "a.pdf")
    assert (Path(config.DATA_DIR) / f"lote_{id_}" / "original.pdf").read_bytes() == dados


def _criar_documento_revisado(id_):
    """Documento revisado (com revisor e campo editado) num lote; devolve o id."""
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        doc = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo, tipo_original, revisor, "
            "revisado_em) VALUES (%s, 1, 1, 1, 'revisado', 'aso', 'holerite', 'ana', now()) RETURNING id",
            (id_,)).fetchone()[0]
        conn.execute(
            "INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, 'nome', 'Ana', 'humano')",
            (doc,))
    return doc


def _documento(doc_id):
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        d = conn.execute("SELECT estado, tipo, tipo_original, revisor FROM documento WHERE id = %s",
                         (doc_id,)).fetchone()
        campos = conn.execute("SELECT campo, valor, origem FROM documento_campos WHERE documento_id = %s",
                              (doc_id,)).fetchall()
    return d, campos


def test_reenvio_com_documento_revisado_da_409_e_preserva_a_revisao(enviar, jobs, sessao):
    dados, id_ = enviar()
    doc = _criar_documento_revisado(id_)
    _estado(id_, "erro")
    with pytest.raises(HTTPException) as e:
        lotes_actions.criar_lote(sessao, dados, dados, "a.pdf")
    assert e.value.status_code == 409
    assert f"lote {id_} possui documentos revisados" in e.value.detail
    assert _estado(id_) == "erro"
    assert jobs == []
    assert _documento(doc) == (("revisado", "aso", "holerite", "ana"), [("nome", "Ana", "humano")])


def test_reenvio_sem_revisao_reprocessa_mesmo_com_documento_classificado(enviar, jobs, sessao):
    dados, id_ = enviar()
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
                     "VALUES (%s, 1, 1, 1, 'classificado', 'aso')", (id_,))
    _estado(id_, "erro")
    resp = lotes_actions.criar_lote(sessao, dados, dados, "a.pdf")
    assert resp["reprocessando"] is True and _estado(id_) == "recebido"
    assert jobs == [(config.FILA_SEGMENTAR, {"lote_id": id_})]


def test_segmentar_e_gravar_nao_apaga_documento_revisado(enviar):
    _, id_ = enviar()
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, 1, 'HOLERITE proventos')", (id_,))
    doc = _criar_documento_revisado(id_)
    _estado(id_, "ocr")
    assert ocr.segmentar_e_gravar(id_) == []
    assert _estado(id_) == "erro"
    assert _documento(doc) == (("revisado", "aso", "holerite", "ana"), [("nome", "Ana", "humano")])
