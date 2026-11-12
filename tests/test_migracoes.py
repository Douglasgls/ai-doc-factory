"""Aplica `alembic upgrade head` e `downgrade base` em um banco descartável criado no mesmo servidor
do DATABASE_URL (como em test_fluxo_banco.py, roda no container api). Pula se não houver Postgres."""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql

from app import config

RAIZ = Path(__file__).resolve().parent.parent
TABELAS = {"empresa", "lote", "documento", "pagina", "perfil_jornada", "analise_ponto", "documento_campos"}


@pytest.fixture
def banco_descartavel():
    try:
        admin = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    nome = "mig_" + uuid.uuid4().hex[:12]
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    partes = urlsplit(config.DATABASE_URL)
    try:
        yield urlunsplit(partes._replace(path="/" + nome))
    finally:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))
        admin.close()


def _alembic(url, *args):
    env = {**os.environ, "DATABASE_URL": url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args], cwd=RAIZ, env=env, capture_output=True, text=True, check=True
    )


def _tabelas(url):
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()
    return {r[0] for r in rows} - {"alembic_version"}


def test_upgrade_head_cria_tabelas_e_downgrade_base_remove(banco_descartavel):
    url = banco_descartavel
    _alembic(url, "upgrade", "head")
    assert _tabelas(url) == TABELAS
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = 'clt_padrao'").fetchone()[0] == 16
        assert conn.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexname IN ('pagina_texto_fts_idx', 'empresa_nome_uniq')"
        ).fetchone()[0] == 2
    _alembic(url, "upgrade", "head")  # idempotente: já está no head
    _alembic(url, "downgrade", "base")
    assert _tabelas(url) == set()
