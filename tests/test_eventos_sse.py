"""Testes para o endpoint SSE (Server-Sent Events), cancelamento, reprocessamento e fan-in de eventos."""
import io
import json
import uuid

import psycopg
from fastapi.testclient import TestClient

from app import config, extracao, ocr
from app.api import app
from app.eventos import (
    limpar_cancelado,
    limpar_tarefas_pos,
    lote_cancelado,
    marcar_cancelado,
    obter_progresso_lote,
    registrar_tarefas_pos,
)
from app.routers.lotes import actions as lotes_actions

client = TestClient(app)


def _pdf_minimo() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (60, 60), "white").save(buf, format="PDF")
    buf.write(f"\n%{uuid.uuid4()}".encode())
    return buf.getvalue()


def test_eventos_lote_sse_retorna_stream_inicial():
    resp = client.post(
        "/lotes",
        files={"arquivo": ("teste_sse.pdf", _pdf_minimo(), "application/pdf")},
    )
    assert resp.status_code == 200
    lote_id = resp.json()["lote_id"]

    sse = client.get(f"/lotes/{lote_id}/eventos?once=true")
    assert sse.status_code == 200
    assert sse.headers["content-type"].startswith("text/event-stream")
    linhas = [l for l in sse.text.splitlines() if l.startswith("data: ")]
    assert len(linhas) >= 1
    pacote = json.loads(linhas[0][len("data: ") :])
    assert pacote["id"] == lote_id
    assert pacote["nome_arquivo"] == "teste_sse.pdf"
    assert pacote["ultimo_evento"]["etapa"] in (
        "recebido",
        "ocr",
        "segmentacao",
        "classificando",
        "extracao",
        "concluido",
    )


def test_cancelar_lote_em_andamento(monkeypatch):
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: None)
    resp = client.post(
        "/lotes",
        files={"arquivo": ("cancelar.pdf", _pdf_minimo(), "application/pdf")},
    )
    assert resp.status_code == 200
    lote_id = resp.json()["lote_id"]

    canc = client.post(f"/lotes/{lote_id}/cancelar")
    assert canc.status_code == 200
    dados = canc.json()
    assert dados["id"] == lote_id
    assert dados["estado"] == "erro"

    sse = client.get(f"/lotes/{lote_id}/eventos?once=true")
    pacote = json.loads([l for l in sse.text.splitlines() if l.startswith("data: ")][0][6:])
    assert pacote["ultimo_evento"]["etapa"] == "cancelado"

    # Reprocessar lote cancelado (em estado 'erro')
    reproc = client.post(f"/lotes/{lote_id}/reprocessar")
    assert reproc.status_code == 200
    assert reproc.json()["estado"] == "recebido"


def test_cancelar_lote_concluido_retorna_409_e_nao_marca_cancelado(monkeypatch):
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: None)
    resp = client.post(
        "/lotes",
        files={"arquivo": ("concluido.pdf", _pdf_minimo(), "application/pdf")},
    )
    lote_id = resp.json()["lote_id"]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE lote SET estado = 'concluido', docs_pendentes = 0 WHERE id = %s", (lote_id,))

    canc = client.post(f"/lotes/{lote_id}/cancelar")
    assert canc.status_code == 409
    assert not lote_cancelado(lote_id)


def test_reprocessar_lote_concluido_ou_revisado_retorna_409_e_preserva_revisao(monkeypatch):
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda *a, **k: None)
    resp = client.post(
        "/lotes",
        files={"arquivo": ("revisado.pdf", _pdf_minimo(), "application/pdf")},
    )
    lote_id = resp.json()["lote_id"]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE lote SET estado = 'concluido', docs_pendentes = 0 WHERE id = %s", (lote_id,))
        doc_id = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
            "VALUES (%s, 1, 1, 1, 'revisado', 'aso') RETURNING id",
            (lote_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO documento_campos (documento_id, campo, valor, origem) "
            "VALUES (%s, 'nome', 'Maria Revisada', 'humano')",
            (doc_id,),
        )

    # Em estado concluído: 409 e não apaga documentos nem campos
    reproc = client.post(f"/lotes/{lote_id}/reprocessar")
    assert reproc.status_code == 409

    # Mesmo se o lote estivesse em erro mas com documento já revisado: 409 e preserva revisão
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("UPDATE lote SET estado = 'erro' WHERE id = %s", (lote_id,))
    reproc_erro = client.post(f"/lotes/{lote_id}/reprocessar")
    assert reproc_erro.status_code == 409

    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        doc_row = conn.execute("SELECT estado, tipo FROM documento WHERE id = %s", (doc_id,)).fetchone()
        campo_row = conn.execute(
            "SELECT valor, origem FROM documento_campos WHERE documento_id = %s AND campo = 'nome'",
            (doc_id,),
        ).fetchone()
    assert doc_row == ("revisado", "aso")
    assert campo_row == ("Maria Revisada", "humano")


def test_cancelar_durante_segmentacao_nao_deixa_lote_em_classificando():
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote_id = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 'race.pdf', 'ocr') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,),
        ).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, 1, 'HOLERITE Ana')", (lote_id,))
    try:
        marcar_cancelado(lote_id)
        ids = ocr.segmentar_e_gravar(lote_id)
        assert ids == []
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            estado, pendentes = conn.execute(
                "SELECT estado, docs_pendentes FROM lote WHERE id = %s", (lote_id,)
            ).fetchone()
        assert estado == "erro"
        assert pendentes == 0
    finally:
        limpar_cancelado(lote_id)
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


def test_lote_multiplos_documentos_so_fecha_stream_apos_ultimo_terminar(monkeypatch):
    monkeypatch.setattr(
        extracao.llm,
        "gemini_gerar",
        lambda *a, **k: {"candidates": [{"content": {"parts": [{"text": '{"nome": "João"}'}]}}]},
    )
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote_id = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) "
            "VALUES (%s, 'multi.pdf', 'concluido', 0) RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,),
        ).fetchone()[0]
        d1 = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
            "VALUES (%s, 1, 1, 1, 'classificado', 'holerite') RETURNING id",
            (lote_id,),
        ).fetchone()[0]
        d2 = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
            "VALUES (%s, 2, 2, 2, 'classificado', 'aso') RETURNING id",
            (lote_id,),
        ).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 1, %s, 'Holerite')", (lote_id, d1))
        conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 2, %s, 'ASO')", (lote_id, d2))

    try:
        registrar_tarefas_pos(lote_id, [f"extracao:{d1}", f"extracao:{d2}"])

        # Primeiro documento termina extração: lote ainda tem d2 pendente!
        extracao.extrair_campos({"documento_id": d1})
        ultimo1, _ = obter_progresso_lote(lote_id)
        assert ultimo1["etapa"] == "extracao"
        pacote1 = lotes_actions.montar_pacote_evento(lote_id)
        assert not lotes_actions._lote_totalmente_finalizado(lote_id, pacote1)

        # Segundo documento termina extração: agora o lote inteiro conclui!
        extracao.extrair_campos({"documento_id": d2})
        ultimo2, _ = obter_progresso_lote(lote_id)
        assert ultimo2["etapa"] == "concluido"
        pacote2 = lotes_actions.montar_pacote_evento(lote_id)
        assert lotes_actions._lote_totalmente_finalizado(lote_id, pacote2)
    finally:
        limpar_tarefas_pos(lote_id)
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


def test_eventos_sse_serializa_confianca_decimal_do_postgres():
    from decimal import Decimal

    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote_id = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) "
            "VALUES (%s, 'decimal.pdf', 'classificando', 1) RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,),
        ).fetchone()[0]
        doc_id = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo, confianca) "
            "VALUES (%s, 1, 1, 1, 'classificado', 'aso', %s) RETURNING id",
            (lote_id, Decimal("0.975")),
        ).fetchone()[0]
    try:
        sse = client.get(f"/lotes/{lote_id}/eventos?once=true")
        assert sse.status_code == 200
        linhas = [l for l in sse.text.splitlines() if l.startswith("data: ")]
        assert len(linhas) == 1
        pacote = json.loads(linhas[0][6:])
        assert pacote["documentos"][0]["id"] == doc_id
        assert pacote["documentos"][0]["confianca"] == 0.975
        assert isinstance(pacote["documentos"][0]["confianca"], float)
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


def test_eventos_e_cancelar_lote_inexistente_retornam_404():
    assert client.get("/lotes/999999/eventos?once=true").status_code == 404
    assert client.post("/lotes/999999/cancelar").status_code == 404
    assert client.post("/lotes/999999/reprocessar").status_code == 404
