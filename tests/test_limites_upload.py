"""Limites do POST /lotes: tamanho (413) e páginas (422), checados antes de gravar. Rodar no compose (Postgres, poppler)."""
import io
import os
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import api, config
from app.routers.lotes import actions as lotes_actions


@pytest.fixture
def cliente(monkeypatch):
    jobs = []
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: jobs.append(a))
    criados = []
    yield TestClient(api.app), criados, jobs
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (criados,))


def _tiff(paginas: int) -> bytes:
    cor = os.getpid() % 200  # bytes únicos por execução
    quadros = [Image.new("RGB", (200 + i, 200), (cor, i, 0)) for i in range(paginas)]
    buf = io.BytesIO()
    quadros[0].save(buf, "TIFF", save_all=True, append_images=quadros[1:])
    return buf.getvalue()


def _estado():
    with psycopg.connect(config.DATABASE_URL) as conn:
        n = conn.execute("SELECT count(*) FROM lote").fetchone()[0]
    pastas = len(list(Path(config.DATA_DIR).glob("lote_*")))
    return n, pastas


def _enviar(http, dados, nome="a.tif"):
    return http.post("/lotes", files={"arquivo": (nome, dados, "image/tiff")})


def test_acima_do_tamanho_da_413_sem_gravar_nada(cliente, monkeypatch):
    http, _, jobs = cliente
    monkeypatch.setattr(config, "UPLOAD_MAX_MB", 1)
    antes = _estado()
    r = _enviar(http, b"%PDF-1.4 " + b"x" * (1024 * 1024 + 10), "grande.pdf")
    assert r.status_code == 413
    assert r.json()["detail"] == "arquivo maior que 1 MB"
    assert _estado() == antes and jobs == []


def test_exatamente_no_limite_de_tamanho_passa(cliente, monkeypatch):
    http, criados, _ = cliente
    monkeypatch.setattr(config, "UPLOAD_MAX_MB", 1)
    dados = b"%PDF-1.4 " + os.urandom(16).hex().encode()
    dados += b"x" * (1024 * 1024 - len(dados))
    r = _enviar(http, dados, "limite.pdf")
    assert r.status_code == 200
    criados.append(r.json()["lote_id"])


def test_acima_das_paginas_da_422_sem_gravar_nada(cliente, monkeypatch):
    http, _, jobs = cliente
    monkeypatch.setattr(config, "UPLOAD_MAX_PAGINAS", 2)
    antes = _estado()
    r = _enviar(http, _tiff(3))  # TIFF multipágina, contado já convertido
    assert r.status_code == 422
    assert r.json()["detail"] == "o lote tem 3 páginas; o máximo é 2"
    assert _estado() == antes and jobs == []


def test_dentro_dos_limites_funciona(cliente, monkeypatch):
    http, criados, jobs = cliente
    monkeypatch.setattr(config, "UPLOAD_MAX_PAGINAS", 2)
    r = _enviar(http, _tiff(2))
    assert r.status_code == 200 and r.json()["existente"] is False
    criados.append(r.json()["lote_id"])
    assert len(jobs) == 1


def test_imagem_invalida_continua_400(cliente):
    http, _, _ = cliente
    assert _enviar(http, b"isto nao e imagem").status_code == 400
