"""Stream SSE de GET /lotes/{id}/eventos: término por fatos verificáveis, frame terminal, teto por tempo,
publicação resiliente e ordem do registro de tarefas pós. Usa o app ASGI de verdade (sem ?once=true)."""
import json
import logging
import shutil
import threading
import time
import uuid
from pathlib import Path

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app import classificar, config, eventos
from app.api import app
from app.eventos import (
    concluir_tarefa_pos,
    publicar_evento,
    registrar_tarefas_pos,
    tarefas_pos_pendentes,
)
from app.routers.lotes import actions as lotes_actions

client = TestClient(app)

PREFIXOS = ("progresso", "historico", "tarefas_pos", "cancelado")


def _chaves_lote(cli) -> set[str]:
    return {k for p in PREFIXOS for k in cli.scan_iter(f"{p}:lote:*")}


@pytest.fixture(autouse=True)
def limpeza():
    """Apaga lotes, chaves do Redis e pastas criados no teste, mesmo se ele falhar."""
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    antes_chaves = _chaves_lote(cli)
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        antes = conn.execute("SELECT COALESCE(MAX(id), 0) FROM lote").fetchone()[0]
    yield
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        ids = [i for (i,) in conn.execute("SELECT id FROM lote WHERE id > %s", (antes,))]
        conn.execute("DELETE FROM lote WHERE id > %s", (antes,))
    novas = _chaves_lote(cli) - antes_chaves
    if novas:
        cli.delete(*novas)
    for i in ids:
        shutil.rmtree(Path(config.DATA_DIR) / f"lote_{i}", ignore_errors=True)


@pytest.fixture(autouse=True)
def teto_de_seguranca(monkeypatch):
    """Se um teste de stream travar, o teto encerra a conexão em vez de pendurar a suíte."""
    monkeypatch.setattr(lotes_actions, "STREAM_TETO_SEGUNDOS", 20)


def _criar_lote(estado: str, docs_pendentes: int = 0) -> int:
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        return conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) VALUES (%s, 'sse.pdf', %s, %s) RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex, estado, docs_pendentes),
        ).fetchone()[0]


def _frames(texto: str) -> list[dict]:
    return [json.loads(l[len("data: "):]) for l in texto.splitlines() if l.startswith("data: ")]


def _stream(lote_id: int) -> tuple[list[dict], float]:
    t0 = time.monotonic()
    resp = client.get(f"/lotes/{lote_id}/eventos")
    assert resp.status_code == 200
    return _frames(resp.text), time.monotonic() - t0


def test_lote_concluido_e_finalizado_encerra_na_hora_com_frame_terminal():
    lote_id = _criar_lote("concluido")
    publicar_evento(lote_id, "concluido", "ok")
    frames, dur = _stream(lote_id)
    assert dur < 3
    assert len(frames) == 1
    assert frames[0]["id"] == lote_id and frames[0]["estado"] == "concluido"
    assert frames[0]["fim"] is True and frames[0]["motivo"] == "finalizado"


def test_concluido_com_ultimo_evento_extracao_e_sem_tarefa_pendente_encerra():
    """Caso reproduzido na revisão: o nome da última etapa não pode mais segurar o stream."""
    lote_id = _criar_lote("concluido")
    publicar_evento(lote_id, "extracao", "extraindo campos...")
    assert tarefas_pos_pendentes(lote_id) == set()
    frames, dur = _stream(lote_id)
    assert dur < 3
    assert frames[-1]["ultimo_evento"]["etapa"] == "extracao"
    assert frames[-1]["fim"] is True and frames[-1]["motivo"] == "finalizado"


def test_concluido_com_tarefa_pos_pendente_so_encerra_quando_a_tarefa_sai():
    lote_id = _criar_lote("concluido")
    registrar_tarefas_pos(lote_id, [f"extracao:{lote_id}"])
    publicar_evento(lote_id, "extracao", "extraindo campos...")

    def concluir():
        time.sleep(2.5)
        concluir_tarefa_pos(lote_id, f"extracao:{lote_id}")
        publicar_evento(lote_id, "concluido", "extração concluída")

    th = threading.Thread(target=concluir)
    th.start()
    frames, dur = _stream(lote_id)
    th.join()
    assert dur >= 2.4  # não encerrou com a tarefa ainda pendente
    assert all("fim" not in f for f in frames[:-1])  # só o último frame é terminal
    assert frames[-1]["fim"] is True and frames[-1]["motivo"] == "finalizado"
    assert frames[-1]["ultimo_evento"]["etapa"] == "concluido"


def test_lote_em_erro_encerra_com_motivo_erro():
    lote_id = _criar_lote("erro")
    frames, dur = _stream(lote_id)
    assert dur < 3
    assert frames[-1]["fim"] is True and frames[-1]["motivo"] == "erro"


def test_teto_de_tempo_encerra_com_tempo_esgotado(monkeypatch):
    monkeypatch.setattr(lotes_actions, "STREAM_TETO_SEGUNDOS", 2)
    lote_id = _criar_lote("classificando", docs_pendentes=1)
    frames, dur = _stream(lote_id)
    assert 1.9 <= dur < 6
    assert "fim" not in frames[0]
    assert frames[-1]["fim"] is True and frames[-1]["motivo"] == "tempo_esgotado"
    assert frames[-1]["estado"] == "classificando"


def test_teto_conta_tempo_real_mesmo_com_mensagens_chegando(monkeypatch):
    """Mensagens no canal fazem get_message voltar na hora; o teto tem de valer por tempo, não por iterações."""
    monkeypatch.setattr(lotes_actions, "STREAM_TETO_SEGUNDOS", 2)
    lote_id = _criar_lote("classificando", docs_pendentes=1)
    parar = threading.Event()

    def inundar():
        while not parar.is_set():
            publicar_evento(lote_id, "classificando", "tick")
            time.sleep(0.05)

    th = threading.Thread(target=inundar)
    th.start()
    try:
        frames, dur = _stream(lote_id)
    finally:
        parar.set()
        th.join()
    assert dur < 6
    assert frames[-1]["fim"] is True and frames[-1]["motivo"] == "tempo_esgotado"
    assert len(frames) > 5  # houve de fato muitas mensagens dentro do teto


def test_publicar_evento_com_redis_indisponivel_nao_levanta_e_registra_warning(caplog):
    morto = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.3)
    with caplog.at_level(logging.WARNING, logger="app.eventos"):
        evento = publicar_evento(123456, "ocr", "teste", r=morto)
    assert evento["etapa"] == "ocr"
    avisos = [x for x in caplog.records if x.levelno == logging.WARNING and "123456" in x.getMessage()]
    assert len(avisos) == 1


def test_cliente_de_modulo_e_reutilizado(monkeypatch):
    monkeypatch.setattr(eventos, "_cliente_modulo", None)
    a = eventos._cliente()
    assert eventos._cliente() is a
    explicito = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    assert eventos._cliente(explicito) is explicito


def _criar_doc_segmentado() -> tuple[int, int]:
    lote_id = _criar_lote("classificando", docs_pendentes=1)
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        doc_id = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado) "
            "VALUES (%s, 1, 1, 1, 'segmentado') RETURNING id",
            (lote_id,),
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 1, %s, %s)",
            (lote_id, doc_id, "HOLERITE proventos descontos liquido a receber Ana Silva"),
        )
    return lote_id, doc_id


def test_classificador_registra_tarefa_pos_antes_do_commit_e_mantem_no_sucesso(monkeypatch):
    lote_id, doc_id = _criar_doc_segmentado()
    vistos = []
    fan_in_real = classificar._fan_in

    def fan_in_espiao(conn, lote):
        vistos.append(tarefas_pos_pendentes(lote))  # ainda dentro da transação
        return fan_in_real(conn, lote)

    monkeypatch.setattr(classificar, "_fan_in", fan_in_espiao)
    classificar.classificar_documento({"documento_id": doc_id})
    assert vistos == [{f"extracao:{doc_id}"}]  # já registrada antes do commit
    assert f"extracao:{doc_id}" in tarefas_pos_pendentes(lote_id)
    with psycopg.connect(config.DATABASE_URL) as conn:
        estado_lote = conn.execute("SELECT estado FROM lote WHERE id = %s", (lote_id,)).fetchone()[0]
    assert estado_lote == "concluido"


def test_falha_na_transacao_do_classificador_nao_deixa_tarefa_orfa(monkeypatch):
    lote_id, doc_id = _criar_doc_segmentado()
    registrar_tarefas_pos(lote_id, ["extracao:outro_doc"])  # tarefa de outro documento não pode ser tocada

    def falhar(conn, lote):
        raise RuntimeError("falha na transação")

    monkeypatch.setattr(classificar, "_fan_in", falhar)
    with pytest.raises(RuntimeError, match="falha na transação"):
        classificar.classificar_documento({"documento_id": doc_id})

    assert tarefas_pos_pendentes(lote_id) == {"extracao:outro_doc"}
    with psycopg.connect(config.DATABASE_URL) as conn:
        estado_doc = conn.execute("SELECT estado FROM documento WHERE id = %s", (doc_id,)).fetchone()[0]
    assert estado_doc == "segmentado"  # a transação foi revertida
