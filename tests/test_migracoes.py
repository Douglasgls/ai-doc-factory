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
TABELAS_SEM_EMPRESA = {"lote", "documento", "pagina", "perfil_jornada", "analise_ponto", "documento_campos"}
TABELAS = TABELAS_SEM_EMPRESA | {"empresa"}  # 0001_baseline
TABELAS_ACESSO = {"tomador", "prestador", "contrato", "usuario"}  # migração 0002
# migração 0004: `empresa` sai, `lote` ganha `contrato_id`
TABELAS_0004 = TABELAS_SEM_EMPRESA | TABELAS_ACESSO
TABELAS_HEAD = TABELAS_0004 | {"convite", "perfil_jornada_cadastro"}  # migrações 0005 e 0010


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


def _colunas_lote(url):
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'lote'").fetchall()
    return {r[0] for r in rows}


def _indices_lote(url):
    with psycopg.connect(url) as conn:
        rows = conn.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'lote'").fetchall()
    return {r[0] for r in rows}


def test_upgrade_head_cria_tabelas_e_downgrade_base_remove(banco_descartavel):
    url = banco_descartavel
    _alembic(url, "upgrade", "head")
    assert _tabelas(url) == TABELAS_HEAD  # sem `empresa`
    assert "contrato_id" in _colunas_lote(url) and "empresa_id" not in _colunas_lote(url)
    assert {"lote_contrato_sha256_uniq", "lote_sem_contrato_sha256_uniq"} <= _indices_lote(url)
    assert "lote_sha256_key" not in _indices_lote(url)
    with psycopg.connect(url) as conn:
        # 17 parâmetros de base (0001 + repouso_semanal_dias) e 3 vigências da EC 141/2026 (migração 0006)
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = 'clt_padrao' AND vigente_desde IS NULL"
                            ).fetchone()[0] == 17
        assert conn.execute(
            "SELECT parametro, vigente_desde::text, valor::int FROM perfil_jornada WHERE vigente_desde IS NOT NULL "
            "ORDER BY parametro, vigente_desde").fetchall() == [
            ('jornada_semanal_min', '2026-12-16', 2520), ('jornada_semanal_min', '2027-12-16', 2400),
            ('repouso_semanal_dias', '2026-12-16', 2)]
        assert conn.execute(
            "SELECT count(*) FROM pg_indexes WHERE indexname IN ('pagina_texto_fts_idx', 'empresa_nome_uniq')"
        ).fetchone()[0] == 1  # empresa_nome_uniq saiu com a tabela
    _alembic(url, "upgrade", "head")  # idempotente: já está no head
    with psycopg.connect(url) as conn:  # 0007: contrato aponta para um perfil; a análise grava o nome
        assert conn.execute("SELECT column_default FROM information_schema.columns WHERE table_name = 'contrato' "
                            "AND column_name = 'perfil_jornada'").fetchone()[0].startswith("'clt_padrao'")
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'analise_ponto' "
                            "AND column_name = 'perfil_nome'").fetchone()[0] == 1
    with psycopg.connect(url) as conn:  # 0009: contrato.proprio, falso para os contratos existentes
        assert conn.execute("SELECT is_nullable, column_default FROM information_schema.columns "
                            "WHERE table_name = 'contrato' AND column_name = 'proprio'").fetchone() == ("NO", "false")
    _alembic(url, "downgrade", "0008_documento_campos_autor")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'contrato' "
                            "AND column_name = 'proprio'").fetchone()[0] == 0
    _alembic(url, "upgrade", "head")
    _alembic(url, "downgrade", "0006_perfil_jornada_vigencia")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE (table_name, column_name) IN "
                            "(('contrato', 'perfil_jornada'), ('analise_ponto', 'perfil_nome'))").fetchone()[0] == 0
    _alembic(url, "downgrade", "0005_convite")  # 0006: volta o perfil sem vigência, com os 16 parâmetros originais
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*), count(DISTINCT parametro) FROM perfil_jornada").fetchone() == (16, 16)
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = 'perfil_jornada' "
                            "AND column_name = 'vigente_desde'").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.UniqueViolation):  # a unicidade antiga voltou
            conn.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                         "VALUES ('clt_padrao', 'jornada_diaria_min', 1, 'min', 'x')")
    _alembic(url, "upgrade", "head")
    with psycopg.connect(url) as conn:
        with pytest.raises(psycopg.errors.UniqueViolation):  # uma única linha de base por parâmetro (NULLs iguais)
            conn.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                         "VALUES ('clt_padrao', 'jornada_diaria_min', 1, 'min', 'x')")
    _alembic(url, "downgrade", "0004_lote_contrato")  # 0005 só cria `convite`
    assert _tabelas(url) == TABELAS_0004
    _alembic(url, "upgrade", "head")
    assert _tabelas(url) == TABELAS_HEAD
    _alembic(url, "downgrade", "0002_modelo_acesso")  # recria `empresa` (vazia) e restaura o UNIQUE de sha256
    assert _tabelas(url) == TABELAS | TABELAS_ACESSO
    assert "empresa_id" in _colunas_lote(url) and "contrato_id" not in _colunas_lote(url)
    assert "lote_sha256_key" in _indices_lote(url)
    _alembic(url, "downgrade", "0001_baseline")  # remove só as tabelas do modelo de acesso
    assert _tabelas(url) == TABELAS
    _alembic(url, "upgrade", "head")
    assert _tabelas(url) == TABELAS_HEAD
    _alembic(url, "downgrade", "base")
    assert _tabelas(url) == set()


def test_downgrade_recusa_mesmo_arquivo_em_dois_contratos(banco_descartavel):
    """O downgrade não apaga lote: com o mesmo sha256 em contratos diferentes ele falha com mensagem clara."""
    url = banco_descartavel
    _alembic(url, "upgrade", "head")
    with psycopg.connect(url, autocommit=True) as conn:
        t = conn.execute("INSERT INTO tomador (nome) VALUES ('T') RETURNING id").fetchone()[0]
        c = []
        for cnpj in ("11222333000181", "12345678000195"):
            p = conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, 'P') RETURNING id",
                             (cnpj,)).fetchone()[0]
            c.append(conn.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s) RETURNING id",
                                  (t, p)).fetchone()[0])
        for contrato in c:
            conn.execute("INSERT INTO lote (sha256, nome_arquivo, contrato_id) VALUES (%s, 'a.pdf', %s)",
                         ("a" * 64, contrato))
    with pytest.raises(subprocess.CalledProcessError) as erro:
        _alembic(url, "downgrade", "0002_modelo_acesso")
    assert "downgrade impossível" in erro.value.stderr
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM lote").fetchone()[0] == 2  # nada foi apagado


def test_0009_contratos_existentes_ficam_nao_proprios(banco_descartavel):
    url = banco_descartavel
    _alembic(url, "upgrade", "0008_documento_campos_autor")
    with psycopg.connect(url, autocommit=True) as conn:
        t = conn.execute("INSERT INTO tomador (nome) VALUES ('T') RETURNING id").fetchone()[0]
        p = conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES ('11222333000181', 'P') RETURNING id"
                         ).fetchone()[0]
        conn.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s)", (t, p))
    _alembic(url, "upgrade", "0009_contrato_proprio")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT proprio FROM contrato").fetchall() == [(False,)]
    _alembic(url, "downgrade", "0008_documento_campos_autor")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM contrato").fetchone()[0] == 1  # o contrato fica, só perde a marca


def test_0010_cadastro_do_perfil_nome_derivado_e_vigencia(banco_descartavel):
    url = banco_descartavel
    _alembic(url, "upgrade", "0009_contrato_proprio")
    with psycopg.connect(url) as conn:  # perfil que já existia antes do cadastro
        conn.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                     "VALUES ('adm_publica', 'jornada_diaria_min', 360, 'min', 'x')")
    _alembic(url, "upgrade", "head")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT perfil, nome, sindicato, vigencia_inicio, vigencia_fim "
                            "FROM perfil_jornada_cadastro ORDER BY perfil").fetchall() == [
            ("adm_publica", "Adm publica", None, None, None), ("clt_padrao", "Padrão", None, None, None)]
        with pytest.raises(psycopg.errors.CheckViolation):  # fim antes do início
            conn.execute("INSERT INTO perfil_jornada_cadastro (perfil, nome, vigencia_inicio, vigencia_fim) "
                         "VALUES ('x', 'X', '2027-01-02', '2027-01-01')")
    with psycopg.connect(url) as conn:
        with pytest.raises(psycopg.errors.CheckViolation):  # nome vazio
            conn.execute("INSERT INTO perfil_jornada_cadastro (perfil, nome) VALUES ('y', '  ')")
    _alembic(url, "downgrade", "0009_contrato_proprio")
    assert "perfil_jornada_cadastro" not in _tabelas(url)
    with psycopg.connect(url) as conn:  # os parâmetros ficam
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = 'adm_publica'").fetchone()[0] == 1


def test_0011_escopo_do_perfil_existentes_nao_gerais_e_sem_dono(banco_descartavel):
    url = banco_descartavel
    _alembic(url, "upgrade", "0010_perfil_jornada_cadastro")
    with psycopg.connect(url) as conn:
        conn.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                     "VALUES ('adm_publica', 'jornada_diaria_min', 360, 'min', 'x')")
        conn.execute("INSERT INTO perfil_jornada_cadastro (perfil, nome) VALUES ('adm_publica', 'Adm publica')")
    _alembic(url, "upgrade", "head")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT perfil, geral, prestador_id FROM perfil_jornada_cadastro ORDER BY perfil"
                            ).fetchall() == [("adm_publica", False, None), ("clt_padrao", False, None)]
        prestador = conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES ('11222333000181', 'P') RETURNING id"
                                 ).fetchone()[0]
        conn.execute("UPDATE perfil_jornada_cadastro SET prestador_id = %s WHERE perfil = 'adm_publica'", (prestador,))
        conn.execute("DELETE FROM prestador WHERE id = %s", (prestador,))  # o perfil fica, sem dono
        assert conn.execute("SELECT prestador_id FROM perfil_jornada_cadastro WHERE perfil = 'adm_publica'"
                            ).fetchone()[0] is None
        conn.commit()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute("UPDATE perfil_jornada_cadastro SET prestador_id = 999999999 WHERE perfil = 'adm_publica'")
    _alembic(url, "downgrade", "0010_perfil_jornada_cadastro")
    with psycopg.connect(url) as conn:
        assert conn.execute("SELECT count(*) FROM information_schema.columns WHERE table_name = "
                            "'perfil_jornada_cadastro' AND column_name IN ('geral', 'prestador_id')").fetchone()[0] == 0
