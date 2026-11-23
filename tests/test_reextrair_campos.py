"""scripts/reextrair_campos.py: seleção dos documentos e dry-run. Postgres/Redis do compose, sem rede."""
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
import redis

from app import config, prompts

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import reextrair_campos  # noqa: E402

ATUAL = prompts.VERSAO_PROMPT_EXTRACAO


@pytest.fixture
def lote():
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote_id = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 't.pdf', 'concluido') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
    yield lote_id
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


def _doc(conn, lote_id, ordem, estado, origem=None):
    i = conn.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo, estado) "
                     "VALUES (%s, %s, %s, %s, 'aso', %s) RETURNING id", (lote_id, ordem, ordem, ordem, estado)).fetchone()[0]
    if origem:
        conn.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, 'nome', 'Maria', %s)",
                     (i, origem))
    return i


def test_selecao_por_versao_e_estado(lote):
    with psycopg.connect(config.DATABASE_URL) as conn:
        antigo = _doc(conn, lote, 1, "classificado", "gemini:gemini-extracao-v3")
        atual = _doc(conn, lote, 2, "classificado", f"gemini:{ATUAL}")
        sem = _doc(conn, lote, 3, "revisado")
        so_humano = _doc(conn, lote, 4, "em_revisao", "humano")
        errado = _doc(conn, lote, 5, "segmentado")
        erro = _doc(conn, lote, 6, "erro", "gemini:gemini-extracao-v3")
        sel = reextrair_campos.selecionar(conn, ATUAL, lote=lote)
    assert dict(sel) == {antigo: "gemini-extracao-v3", sem: reextrair_campos.SEM_EXTRACAO,
                         so_humano: reextrair_campos.SEM_EXTRACAO}
    assert atual not in dict(sel) and errado not in dict(sel) and erro not in dict(sel)


def test_limite_e_filtro_de_lote(lote):
    with psycopg.connect(config.DATABASE_URL) as conn:
        ids = [_doc(conn, lote, n, "classificado") for n in (1, 2, 3)]
        assert [i for i, _ in reextrair_campos.selecionar(conn, ATUAL, lote=lote, limite=2)] == ids[:2]
        assert reextrair_campos.selecionar(conn, ATUAL, lote=lote + 10**9) == []


def test_dry_run_nao_enfileira(lote, capsys):
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = _doc(conn, lote, 1, "classificado")
    r = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    antes = r.llen(config.FILA_EXTRAIR)
    assert reextrair_campos.main(["--lote", str(lote)]) == 0
    saida = capsys.readouterr().out
    assert "dry-run" in saida and str(doc) in saida and "(sem extração): 1" in saida
    assert r.llen(config.FILA_EXTRAIR) == antes


def test_executar_enfileira_com_o_payload_de_sempre(lote):
    with psycopg.connect(config.DATABASE_URL) as conn:
        doc = _doc(conn, lote, 1, "classificado", "gemini:gemini-extracao-v3")
    r = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    r.delete(config.FILA_EXTRAIR)
    assert reextrair_campos.main(["--lote", str(lote), "--executar"]) == 0
    import json
    itens = [json.loads(x) for x in r.lrange(config.FILA_EXTRAIR, 0, -1)]
    assert [i["payload"] for i in itens] == [{"documento_id": doc}]
    r.delete(config.FILA_EXTRAIR)
