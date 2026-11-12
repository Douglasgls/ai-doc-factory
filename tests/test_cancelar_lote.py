"""Cancelamento de lote: preserva classificação já feita, não trava com o classificador e só mexe no Redis
depois do commit. Tudo pelo fluxo real (rotas e handlers), com banco e Redis de verdade."""
import threading
import time
import uuid

import psycopg
import pytest
import redis
from fastapi.testclient import TestClient

from app import analise, classificar, config, extracao
from app.api import app
from app.eventos import (
    limpar_cancelado,
    limpar_tarefas_pos,
    lote_cancelado,
    obter_progresso_lote,
    registrar_tarefas_pos,
    tarefas_pos_pendentes,
)
from app.routers import r
from app.routers.lotes import actions as lotes_actions
from app.routers.revisao import actions as revisao_actions

client = TestClient(app)


@pytest.fixture
def novo_lote():
    """Fábrica de lotes com documentos nos estados pedidos; limpa banco e Redis no fim."""
    criados: list[int] = []

    def criar(estado: str, docs_pendentes: int, docs: list[tuple[str, str | None]]):
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            lote_id = conn.execute(
                "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) VALUES (%s, 'cancelar.pdf', %s, %s) "
                "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex, estado, docs_pendentes)).fetchone()[0]
            criados.append(lote_id)
            ids = []
            for ordem, (est, tipo) in enumerate(docs, 1):
                ids.append(conn.execute(
                    "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", (lote_id, ordem, ordem, ordem, est, tipo),
                ).fetchone()[0])
        return lote_id, ids

    yield criar
    for lote_id in criados:
        limpar_cancelado(lote_id, r)
        limpar_tarefas_pos(lote_id, r)
        r.delete(f"progresso:lote:{lote_id}", f"historico:lote:{lote_id}")
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        for lote_id in criados:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


def _estados(lote_id: int) -> tuple[str, int, list[str]]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        lote = conn.execute("SELECT estado, docs_pendentes FROM lote WHERE id = %s", (lote_id,)).fetchone()
        docs = [e for (e,) in conn.execute("SELECT estado FROM documento WHERE lote_id = %s ORDER BY ordem", (lote_id,))]
    return lote[0], lote[1], docs


def test_a_classificando_so_segmentado_vira_erro(novo_lote):
    lote_id, _ = novo_lote("classificando", 1, [("classificado", "holerite"), ("em_revisao", "aso"),
                                                 ("revisado", "holerite"), ("segmentado", None)])
    resp = client.post(f"/lotes/{lote_id}/cancelar")
    assert resp.status_code == 200
    assert _estados(lote_id) == ("erro", 0, ["classificado", "em_revisao", "revisado", "erro"])
    assert lote_cancelado(lote_id, r)


def test_cancelar_duas_vezes_e_idempotente(novo_lote):
    lote_id, _ = novo_lote("ocr", 0, [])
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 200
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 200
    assert _estados(lote_id) == ("erro", 0, [])


def test_b_concluido_com_tarefa_pos_preserva_lote_e_documentos(novo_lote):
    lote_id, _ = novo_lote("concluido", 0, [("classificado", "folha_ponto"), ("em_revisao", "aso"),
                                             ("revisado", "holerite")])
    registrar_tarefas_pos(lote_id, ["extracao:1", "analise:1"], r)
    resp = client.post(f"/lotes/{lote_id}/cancelar")
    assert resp.status_code == 200
    assert resp.json()["estado"] == "concluido"
    assert _estados(lote_id) == ("concluido", 0, ["classificado", "em_revisao", "revisado"])
    assert tarefas_pos_pendentes(lote_id, r) == set()
    assert obter_progresso_lote(lote_id, r)[0]["etapa"] == "concluido"  # acompanhamento encerra


def test_409_lote_concluido_sem_pendencia_e_404(novo_lote):
    lote_id, _ = novo_lote("concluido", 0, [("classificado", "holerite")])
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 409
    assert not lote_cancelado(lote_id, r)
    assert client.post("/lotes/999999999/cancelar").status_code == 404


def test_lote_concluido_com_revisado_pode_cancelar_pendencia(novo_lote):
    # o 409 antigo por 'revisado' perdeu o sentido: cancelar não toca mais em documento revisado
    lote_id, _ = novo_lote("concluido", 0, [("revisado", "holerite")])
    registrar_tarefas_pos(lote_id, ["extracao:1"], r)
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 200
    assert _estados(lote_id) == ("concluido", 0, ["revisado"])


def test_c_revisao_humana_depois_do_cancelar_enfileira_e_handlers_nao_sao_barrados(
        novo_lote, extracoes, monkeypatch):
    lote_id, (d_ponto, d_rev) = novo_lote("concluido", 0, [("classificado", "holerite"), ("em_revisao", "aso")])
    registrar_tarefas_pos(lote_id, [f"extracao:{d_ponto}", f"extracao:{d_rev}"], r)
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 200
    assert lote_cancelado(lote_id, r)

    analises = []
    monkeypatch.setattr(revisao_actions, "enfileirar_analise", lambda doc, cli=None: analises.append(doc))
    from app.routers.documentos import actions as documentos_actions
    monkeypatch.setattr(documentos_actions, "enfileirar_analise", lambda doc, cli=None: analises.append(doc))

    # PATCH /documentos/{id}/tipo: classificado -> folha_ponto
    resp = client.patch(f"/documentos/{d_ponto}/tipo", json={"tipo": "folha_ponto", "revisor": "ana"})
    assert resp.status_code == 200
    assert not lote_cancelado(lote_id, r)
    assert d_ponto in extracoes and analises == [d_ponto]

    # o handler de extração de verdade não é barrado (sem rede, cai no caminho de LLM indisponível)
    extracao.extrair_campos({"documento_id": d_ponto})
    assert obter_progresso_lote(lote_id, r)[0]["mensagem"].startswith("Processamento concluído")

    # o handler de análise de verdade também passa da checagem da flag
    class Passou(Exception):
        pass

    def analisar_falso(*a, **k):
        raise Passou
    monkeypatch.setattr(analise, "analisar", analisar_falso)
    with pytest.raises(Passou):
        analise.analisar_documento({"documento_id": d_ponto})

    # POST /documentos/{id}/revisao: cancela de novo e revisa o outro documento
    assert client.post(f"/lotes/{lote_id}/cancelar").status_code == 200
    assert lote_cancelado(lote_id, r)
    resp = client.post(f"/documentos/{d_rev}/revisao", json={"tipo": "folha_ponto", "revisor": "ana"})
    assert resp.status_code == 200
    assert not lote_cancelado(lote_id, r)
    assert d_rev in extracoes and d_rev in analises
    assert _estados(lote_id) == ("concluido", 0, ["revisado", "revisado"])


class _ConnAtrasada:
    """Proxy de conexão: atrasa (ou quebra) em certos comandos SQL, para abrir a janela da corrida."""

    def __init__(self, real, atraso_apos: str | None, atraso: float, falha_em: str | None):
        self._real, self._apos, self._atraso, self._falha = real, atraso_apos, atraso, falha_em

    def execute(self, sql, *a, **k):
        if self._falha and sql.lstrip().startswith(self._falha):
            raise psycopg.OperationalError("falha injetada no banco")
        res = self._real.execute(sql, *a, **k)
        if self._apos and sql.lstrip().startswith(self._apos):
            time.sleep(self._atraso)
        return res

    def __enter__(self):
        self._real.__enter__()
        return self

    def __exit__(self, *exc):
        return self._real.__exit__(*exc)

    def __getattr__(self, nome):
        return getattr(self._real, nome)


def _conn_proxy(monkeypatch, modulo, apos=None, atraso=0.0, falha_em=None):
    real = psycopg.connect

    class Falso:
        connect = staticmethod(lambda *a, **k: _ConnAtrasada(real(*a, **k), apos, atraso, falha_em))
        OperationalError = psycopg.OperationalError
    monkeypatch.setattr(modulo, "psycopg", Falso)


def _correr(alvos: list, intervalo: float = 0.25) -> list[BaseException]:
    erros: list[BaseException] = []

    def rodar(f):
        try:
            f()
        except BaseException as e:  # noqa: BLE001 - a corrida quer ver qualquer exceção
            erros.append(e)
    threads = [threading.Thread(target=rodar, args=(f,)) for f in alvos]
    for t in threads:
        t.start()
        time.sleep(intervalo)
    for t in threads:
        t.join(30)
    return erros


def test_d_corrida_classificador_primeiro(novo_lote, monkeypatch):
    lote_id, (d1, d2) = novo_lote("classificando", 2, [("segmentado", None), ("segmentado", None)])
    original = classificar._fan_in

    def fan_in_lento(conn, lid):  # segura o bloqueio do documento antes de tocar no lote
        time.sleep(0.8)
        return original(conn, lid)
    monkeypatch.setattr(classificar, "_fan_in", fan_in_lento)
    erros = _correr([lambda: classificar.classificar_documento({"documento_id": d1}),
                     lambda: lotes_actions.cancelar_lote(lote_id)])
    assert erros == []
    estado, pendentes, docs = _estados(lote_id)
    assert (estado, pendentes) == ("erro", 0)
    assert docs[0] in ("classificado", "em_revisao") and docs[1] == "erro"  # a classificação feita foi mantida
    assert lote_cancelado(lote_id, r)


def test_d_corrida_cancelar_primeiro(novo_lote, monkeypatch):
    lote_id, (d1, d2) = novo_lote("classificando", 2, [("segmentado", None), ("segmentado", None)])
    _conn_proxy(monkeypatch, lotes_actions, apos="UPDATE documento", atraso=0.8)
    erros = _correr([lambda: lotes_actions.cancelar_lote(lote_id),
                     lambda: classificar.classificar_documento({"documento_id": d1})])
    assert erros == []
    # o job em voo perdeu a corrida: não classifica, não decrementa, não reabre o lote
    assert _estados(lote_id) == ("erro", 0, ["erro", "erro"])
    assert lote_cancelado(lote_id, r)
    classificar.classificar_documento({"documento_id": d2})  # job repetido depois do cancelar: nada muda
    assert _estados(lote_id) == ("erro", 0, ["erro", "erro"])


def test_d_dois_cliques_simultaneos(novo_lote, monkeypatch):
    lote_id, _ = novo_lote("classificando", 1, [("classificado", "holerite"), ("segmentado", None)])
    _conn_proxy(monkeypatch, lotes_actions, apos="UPDATE documento", atraso=0.5)
    erros = _correr([lambda: lotes_actions.cancelar_lote(lote_id)] * 2, intervalo=0.1)
    assert erros == []
    assert _estados(lote_id) == ("erro", 0, ["classificado", "erro"])


def test_e_falha_do_banco_nao_grava_flag_nem_limpa_tarefas(novo_lote, monkeypatch):
    lote_id, _ = novo_lote("classificando", 1, [("segmentado", None)])
    registrar_tarefas_pos(lote_id, ["extracao:1"], r)
    _conn_proxy(monkeypatch, lotes_actions, falha_em="UPDATE lote")
    with pytest.raises(psycopg.OperationalError):
        lotes_actions.cancelar_lote(lote_id)
    assert not lote_cancelado(lote_id, r)
    assert tarefas_pos_pendentes(lote_id, r) == {"extracao:1"}
    assert obter_progresso_lote(lote_id, r)[0] is None
    monkeypatch.undo()
    assert _estados(lote_id) == ("classificando", 1, ["segmentado"])  # rollback do UPDATE de documento


def test_e_falha_do_redis_depois_do_commit_nao_vira_500(novo_lote, monkeypatch):
    lote_id, _ = novo_lote("classificando", 1, [("segmentado", None)])

    def quebra(*a, **k):
        raise redis.ConnectionError("redis fora")
    monkeypatch.setattr(lotes_actions, "marcar_cancelado", quebra)
    monkeypatch.setattr(lotes_actions, "limpar_tarefas_pos", quebra)
    resp = client.post(f"/lotes/{lote_id}/cancelar")
    assert resp.status_code == 200
    assert _estados(lote_id) == ("erro", 0, ["erro"])


def test_e_redis_totalmente_fora_nao_vira_500(novo_lote, monkeypatch):
    lote_id, _ = novo_lote("classificando", 1, [("segmentado", None)])
    fora = redis.Redis(host="127.0.0.1", port=1, socket_connect_timeout=0.2)
    monkeypatch.setattr(lotes_actions, "r", fora)
    resp = client.post(f"/lotes/{lote_id}/cancelar")
    assert resp.status_code == 200
    assert resp.json()["estado"] == "erro"
    assert _estados(lote_id) == ("erro", 0, ["erro"])
