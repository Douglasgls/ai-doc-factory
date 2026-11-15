"""Compara `Base.metadata` (app/models) com o schema real obtido de `alembic upgrade head` em um banco
descartável no mesmo servidor do DATABASE_URL. Pula se não houver Postgres."""
import os
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, PrimaryKeyConstraint, UniqueConstraint

from app import config
from app.database import get_session, url_sqlalchemy
from app.models import Base

RAIZ = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def schema_real():
    try:
        admin = psycopg.connect(config.DATABASE_URL, autocommit=True, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    nome = "mod_" + uuid.uuid4().hex[:12]
    admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(nome)))
    url = urlunsplit(urlsplit(config.DATABASE_URL)._replace(path="/" + nome))
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=RAIZ, env={**os.environ, "DATABASE_URL": url}, capture_output=True, text=True, check=True,
        )
        with psycopg.connect(url) as conn:
            colunas = {
                (t, c): (nulo == "YES", padrao is not None)
                for t, c, nulo, padrao in conn.execute(
                    "SELECT table_name, column_name, is_nullable, column_default FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
                )
            }
            indices = {r[0] for r in conn.execute(
                "SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename <> 'alembic_version'")}
            restricoes = {
                (t, n, tp) for t, n, tp in conn.execute(
                    "SELECT c.conrelid::regclass::text, c.conname, c.contype FROM pg_constraint c "
                    "JOIN pg_namespace n ON n.oid = c.connamespace WHERE n.nspname = 'public' "
                    "AND c.conrelid::regclass::text <> 'alembic_version' AND c.contype IN ('c', 'u', 'f')")
            }
        yield {"colunas": colunas, "indices": indices, "restricoes": restricoes}
    finally:
        admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(nome)))
        admin.close()


def test_tabelas_do_metadata_existem_no_schema(schema_real):
    tabelas_reais = {t for t, _ in schema_real["colunas"]}
    assert set(Base.metadata.tables) == tabelas_reais


def test_colunas_nulabilidade_e_default(schema_real):
    modelo = {}
    for tabela in Base.metadata.tables.values():
        for col in tabela.columns:
            tem_padrao = (
                col.server_default is not None
                or (col.primary_key and col.autoincrement is True and col.type.python_type is int)
            )
            modelo[(tabela.name, col.name)] = (col.nullable, tem_padrao)
    assert modelo == schema_real["colunas"]


def test_indices_e_restricoes(schema_real):
    indices = set()
    restricoes = set()
    for tabela in Base.metadata.tables.values():
        indices |= {i.name for i in tabela.indexes}
        indices.add(f"{tabela.name}_pkey")
        for rc in tabela.constraints:
            if isinstance(rc, UniqueConstraint) and rc.name:
                restricoes.add((tabela.name, rc.name, "u"))
                indices.add(rc.name)
            elif isinstance(rc, CheckConstraint):
                restricoes.add((tabela.name, rc.name, "c"))
        for col in tabela.columns:
            if col.unique:
                nome = f"{tabela.name}_{col.name}_key"
                restricoes.add((tabela.name, nome, "u"))
                indices.add(nome)
        for fk in tabela.foreign_key_constraints:
            restricoes.add((tabela.name, f"{tabela.name}_{fk.columns.keys()[0]}_fkey", "f"))
    assert indices == schema_real["indices"]
    assert restricoes == schema_real["restricoes"]


def test_url_sqlalchemy_usa_psycopg_v3():
    assert url_sqlalchemy("postgresql://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert url_sqlalchemy("postgres://u:p@h/d") == "postgresql+psycopg://u:p@h/d"
    assert url_sqlalchemy("postgresql+psycopg://u:p@h/d") == "postgresql+psycopg://u:p@h/d"


def test_get_session_commit_rollback_e_fecha(monkeypatch):
    from app import database

    eventos = []

    class Falsa:
        def commit(self): eventos.append("commit")
        def rollback(self): eventos.append("rollback")
        def close(self): eventos.append("close")

    monkeypatch.setattr(database, "SessionLocal", lambda: Falsa())
    gen = get_session()
    next(gen)
    with pytest.raises(StopIteration):
        next(gen)
    assert eventos == ["commit", "close"]

    eventos.clear()
    gen = get_session()
    next(gen)
    with pytest.raises(ValueError):
        gen.throw(ValueError("x"))
    assert eventos == ["rollback", "close"]
