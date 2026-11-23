"""Contra o Postgres do compose: docker compose exec api python -m pytest tests"""
import uuid

import psycopg
import pytest

from app import config, ocr
from app.classificar import classificar_documento

TEXTOS = [
    "HOLERITE Ana Página 1 de 2", "HOLERITE Ana Página 2 de 2", "",
    "HOLERITE Bruno Página 1 de 1", "ATESTADO MÉDICO paciente CID afastamento consulta",
]


@pytest.fixture
def lote():
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        id_ = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 'teste.pdf', 'ocr') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,),
        ).fetchone()[0]
        for n, t in enumerate(TEXTOS, start=1):
            conn.execute("INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, %s, %s)", (id_, n, t))
    yield id_
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (id_,))


def _lote(id_):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (id_,)).fetchone()


def _docs(id_):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute(
            "SELECT id, pagina_ini, pagina_fim, estado FROM documento WHERE lote_id = %s ORDER BY ordem", (id_,)
        ).fetchall()


def test_segmentar_cria_documentos_vincula_paginas_e_refaz_sem_duplicar(lote):
    ids = ocr.segmentar_e_gravar(lote)
    assert [(i, f) for _, i, f, _ in _docs(lote)] == [(1, 3), (4, 4), (5, 5)]
    assert _lote(lote) == ("classificando", 3)
    with psycopg.connect(config.DATABASE_URL) as conn:
        sem_doc = conn.execute(
            "SELECT count(*) FROM pagina WHERE lote_id = %s AND documento_id IS NULL", (lote,)
        ).fetchone()[0]
        assert sem_doc == 0
        conn.execute("UPDATE lote SET estado = 'erro' WHERE id = %s", (lote,))  # reprocesso após erro
    novos = ocr.segmentar_e_gravar(lote)
    assert len(_docs(lote)) == 3 and set(novos).isdisjoint(ids)
    assert ocr.segmentar_e_gravar(lote) == []  # já classificando: não refaz


def test_fan_in_sem_decremento_duplo_e_conclui(lote):
    ids = ocr.segmentar_e_gravar(lote)
    classificar_documento({"documento_id": ids[0]})
    classificar_documento({"documento_id": ids[0]})  # job repetido
    assert _lote(lote) == ("classificando", 2)
    for i in ids[1:]:
        classificar_documento({"documento_id": i})
    classificar_documento({"documento_id": ids[2]})
    assert _lote(lote) == ("concluido", 0)
    assert {e for *_, e in _docs(lote)} <= {"classificado", "em_revisao"}  # decidido, sem ficar segmentado


def test_segmentar_lote_repetido_em_classificando_so_reenfileira_pendentes(lote, monkeypatch):
    ids = ocr.segmentar_e_gravar(lote)
    classificar_documento({"documento_id": ids[0]})
    enfileirados = []
    monkeypatch.setattr(ocr, "_enfileirar_classificacao", enfileirados.extend)
    monkeypatch.setattr(ocr, "pdfinfo_from_path", lambda *_: pytest.fail("não deve refazer OCR"))
    ocr.processar_lote({"lote_id": lote})
    assert enfileirados == ids[1:]
    assert [d[0] for d in _docs(lote)] == ids and _lote(lote) == ("classificando", 2)


def test_segmentar_lote_repetido_em_concluido_nao_faz_nada(lote, monkeypatch):
    for i in ocr.segmentar_e_gravar(lote):
        classificar_documento({"documento_id": i})
    monkeypatch.setattr(ocr, "_enfileirar_classificacao", lambda ids: pytest.fail("nada a enfileirar"))
    ocr.processar_lote({"lote_id": lote})
    assert _lote(lote) == ("concluido", 0)


def test_falha_no_ocr_so_marca_erro_ao_esgotar_as_tentativas(lote, monkeypatch):
    from app.filas import enfileirar, processar_um
    import redis
    eventos = []
    monkeypatch.setattr(ocr, "publicar_evento", lambda lid, etapa, *a, **k: eventos.append(etapa))

    def quebra(*_):
        raise RuntimeError("pdf ilegivel")

    monkeypatch.setattr(ocr, "pdfinfo_from_path", quebra)
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    fila = f"teste_{uuid.uuid4().hex[:8]}"
    try:
        enfileirar(cli, fila, {"lote_id": lote})
        for tentativa in range(1, config.MAX_TENTATIVAS + 1):
            assert processar_um(cli, fila, ocr.processar_lote, timeout=1, ao_esgotar=ocr.marcar_erro_lote)
            if tentativa < config.MAX_TENTATIVAS:
                assert _lote(lote)[0] == "ocr" and "erro" not in eventos
        assert _lote(lote)[0] == "erro" and eventos.count("erro") == 1
    finally:
        cli.delete(fila, f"{fila}:proc", f"{fila}:atrasados")
        for x in cli.lrange("dlq", 0, -1):
            if f'"{fila}"' in x:
                cli.lrem("dlq", 0, x)
