"""Testes para o endpoint SSE (Server-Sent Events) e cancelamento de lotes via Redis Pub/Sub."""
import io
import json
import uuid

from fastapi.testclient import TestClient

from app.api import app

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


def test_cancelar_lote_em_andamento():
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

    # Reprocessar lote cancelado
    reproc = client.post(f"/lotes/{lote_id}/reprocessar")
    assert reproc.status_code == 200
    assert reproc.json()["estado"] in ("recebido", "ocr", "classificando", "concluido")


def test_eventos_e_cancelar_lote_inexistente_retornam_404():
    assert client.get("/lotes/999999/eventos?once=true").status_code == 404
    assert client.post("/lotes/999999/cancelar").status_code == 404
    assert client.post("/lotes/999999/reprocessar").status_code == 404

