"""Perfil de jornada por contrato: herança de clt_padrao, API (só plataforma) e worker de análise usando o perfil do
contrato do lote. Contra o Postgres e o Redis; o Gemini e o Jev são mockados (fixture `rede`)."""
import uuid
from datetime import date

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import analise, config
from app.api import app
from app.ponto import PERFIL_PADRAO, carregar_perfil, herdar, vigente
from app.routers.auth.actions import UsuarioContexto, exigir_usuario
from tests.test_analise import IRREGULAR, _doc, _gemini, _jev, rede  # noqa: F401

client = TestClient(app)


@pytest.fixture
def nome():
    """Nome de perfil só deste teste; as linhas são apagadas no fim."""
    n = "teste_" + uuid.uuid4().hex[:12]
    yield n
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM perfil_jornada WHERE perfil = %s", (n,))


def _p(parametro, valor, vigente_desde=None, base_legal="ACT de teste, cláusula 1ª"):
    return {"parametro": parametro, "valor": valor, "base_legal": base_legal, "vigente_desde": vigente_desde}


def _gravar(nome, *parametros):
    return client.put(f"/perfis-jornada/{nome}", json={"parametros": list(parametros)})


# ---------- herança (função pura) ----------

def test_herdar_guarda_so_o_que_difere_e_substitui_a_linha_do_tempo_do_parametro():
    padrao = [("a", 1, "lei a", None), ("b", 10, "lei b", None), ("b", 20, "lei b nova", date(2026, 12, 16))]
    efetivo = herdar(padrao, [("b", 15, "acordo", None)])
    assert efetivo == {"a": {"valor": 1.0, "base_legal": "lei a"}, "b": {"valor": 15.0, "base_legal": "acordo"}}
    assert vigente(efetivo, "b", date(2030, 1, 1)) == (15.0, "acordo")  # a vigência do padrão não vaza para o perfil
    proprio = herdar(padrao, [("b", 15, "acordo", None), ("b", 12, "aditivo", date(2027, 3, 1))])
    assert [v["desde"] for v in proprio["b"]["vigencias"]] == ["2027-03-01"]
    assert herdar(padrao, padrao) == herdar(padrao, [])  # o próprio padrão


# ---------- API ----------

def test_cria_consulta_e_lista_perfil_com_heranca(nome):
    r = _gravar(nome, _p("jornada_semanal_min", 2640), _p("extras_max_dia_min", 90),
                _p("extras_max_dia_min", 60, "2027-01-01"))
    assert r.status_code == 200, r.text
    corpo = r.json()
    assert corpo["perfil"] == nome and corpo["padrao"] is False
    assert [(p["parametro"], p["valor"], p["vigente_desde"], p["unidade"]) for p in corpo["proprios"]] == [
        ("extras_max_dia_min", 90, None, "min"), ("extras_max_dia_min", 60, "2027-01-01", "min"),
        ("jornada_semanal_min", 2640, None, "min")]
    efetivo = corpo["efetivo"]
    assert efetivo["jornada_semanal_min"] == {"valor": 2640, "base_legal": "ACT de teste, cláusula 1ª"}  # sem vigências
    assert efetivo["extras_max_dia_min"]["vigencias"] == [
        {"desde": "2027-01-01", "valor": 60, "base_legal": "ACT de teste, cláusula 1ª"}]
    padrao = client.get(f"/perfis-jornada/{PERFIL_PADRAO}").json()
    assert padrao["padrao"] is True and set(efetivo) == set(padrao["efetivo"])
    for herdado in ("jornada_diaria_min", "repouso_semanal_dias", "interjornada_min"):  # o resto vem de clt_padrao
        assert efetivo[herdado] == padrao["efetivo"][herdado]
    assert [v["desde"] for v in padrao["efetivo"]["jornada_semanal_min"]["vigencias"]] == ["2026-12-16", "2027-12-16"]
    assert client.get(f"/perfis-jornada/{nome}").json() == corpo
    lista = {p["perfil"]: p for p in client.get("/perfis-jornada").json()}
    assert lista[nome] == {"perfil": nome, "padrao": False, "parametros_proprios": 2, "contratos": 0}
    assert lista[PERFIL_PADRAO]["padrao"] is True and lista[PERFIL_PADRAO]["parametros_proprios"] == 17


def test_gravar_de_novo_substitui_sem_duplicar(nome):
    assert _gravar(nome, _p("jornada_semanal_min", 2640), _p("extras_max_dia_min", 90)).status_code == 200
    r = _gravar(nome, _p("extras_max_dia_min", 100))
    assert r.status_code == 200 and [p["parametro"] for p in r.json()["proprios"]] == ["extras_max_dia_min"]
    assert _gravar(nome, _p("extras_max_dia_min", 100)).json() == r.json()  # idempotente
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = %s", (nome,)).fetchone()[0] == 1
        assert carregar_perfil(conn, nome)["extras_max_dia_min"]["valor"] == 100.0
        assert carregar_perfil(conn, nome)["jornada_semanal_min"] == carregar_perfil(conn)["jornada_semanal_min"]


def test_validacoes_do_perfil(nome):
    assert _gravar(PERFIL_PADRAO, _p("extras_max_dia_min", 1)).status_code == 409  # a referência não muda pela API
    assert _gravar(nome, _p("parametro_inventado", 1)).status_code == 422
    assert _gravar(nome, _p("extras_max_dia_min", 60, "2027-01-01")).status_code == 422  # sem valor de base
    assert _gravar(nome, _p("extras_max_dia_min", 1), _p("extras_max_dia_min", 2)).status_code == 422  # repetido
    assert _gravar(nome, _p("extras_max_dia_min", -1)).status_code == 422
    assert _gravar(nome, _p("extras_max_dia_min", 1, base_legal="  ")).status_code == 422
    assert client.put(f"/perfis-jornada/{nome}", json={"parametros": []}).status_code == 422
    assert _gravar("Nome-Invalido", _p("extras_max_dia_min", 1)).status_code == 422
    assert client.get(f"/perfis-jornada/{nome}").status_code == 404  # nada foi gravado
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = %s", (nome,)).fetchone()[0] == 0
        with pytest.raises(ValueError):
            carregar_perfil(conn, nome)


def test_associa_perfil_ao_contrato(nome, orgs):
    contrato = orgs.contrato()
    antes = [c for c in client.get("/contratos").json() if c["id"] == contrato]
    assert antes[0]["perfil_jornada"] == PERFIL_PADRAO  # padrão de todo contrato
    assert client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": nome}).status_code == 404  # perfil não existe
    assert _gravar(nome, _p("extras_max_dia_min", 90)).status_code == 200
    r = client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": nome})
    assert r.status_code == 200 and r.json()["id"] == contrato and r.json()["perfil_jornada"] == nome
    assert [c["perfil_jornada"] for c in client.get("/contratos").json() if c["id"] == contrato] == [nome]
    assert {p["perfil"]: p["contratos"] for p in client.get("/perfis-jornada").json()}[nome] == 1
    assert client.put(f"/contratos/{2 ** 62}/perfil-jornada", json={"perfil": nome}).status_code == 404
    assert client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": "Nome Invalido"}).status_code == 422
    volta = client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": PERFIL_PADRAO})
    assert volta.status_code == 200 and volta.json()["perfil_jornada"] == PERFIL_PADRAO


@pytest.mark.parametrize("nivel", ["tomador", "prestador"])
def test_so_a_plataforma_cadastra_e_associa(nivel, nome, orgs):
    contrato = orgs.contrato()
    with psycopg.connect(config.DATABASE_URL) as conn:
        tomador, prestador = conn.execute("SELECT tomador_id, prestador_id FROM contrato WHERE id = %s",
                                          (contrato,)).fetchone()
    dono = UsuarioContexto(id=0, email="x@exemplo.invalid", nome="X", nivel=nivel, papel="admin",
                           tomador_id=tomador if nivel == "tomador" else None,
                           prestador_id=prestador if nivel == "prestador" else None)
    app.dependency_overrides[exigir_usuario] = lambda: dono  # a fixture `autenticacao` desfaz no fim
    assert client.get("/perfis-jornada").status_code == 403
    assert client.get(f"/perfis-jornada/{PERFIL_PADRAO}").status_code == 403
    assert _gravar(nome, _p("extras_max_dia_min", 90)).status_code == 403
    # nem no próprio contrato: a associação é da plataforma
    assert client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": PERFIL_PADRAO}).status_code == 403
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM perfil_jornada WHERE perfil = %s", (nome,)).fetchone()[0] == 0


# ---------- worker de análise ----------

def _analisar(rede, doc, marcacoes=IRREGULAR):
    rede["gemini"].append(_gemini(marcacoes))
    rede["jev"].append(lambda corpo: _jev(corpo, {}))
    analise.analisar_documento({"documento_id": doc})
    with psycopg.connect(config.DATABASE_URL) as conn:
        return conn.execute("SELECT perfil_nome, perfil, divergencias FROM analise_ponto WHERE documento_id = %s",
                            (doc,)).fetchone()


@pytest.fixture
def doc_do_contrato(orgs):
    """(contrato, documento folha_ponto em um lote desse contrato); `orgs` apaga o lote no fim."""
    contrato = orgs.contrato()
    lote, doc = _doc()
    orgs.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (contrato, lote))
    return contrato, doc


def test_worker_usa_o_perfil_do_contrato_do_lote(rede, nome, doc_do_contrato):  # noqa: F811
    contrato, doc = doc_do_contrato
    perfil_nome, perfil, divs = _analisar(rede, doc)  # contrato novo: clt_padrao
    assert perfil_nome == PERFIL_PADRAO and perfil["extras_max_dia_min"]["valor"] == 120
    assert "horas_extras_acima_limite" in [d["tipo"] for d in divs]  # 4h extras no dia 03/11
    assert _gravar(nome, _p("extras_max_dia_min", 300, base_legal="ACT de teste")).status_code == 200
    assert client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": nome}).status_code == 200
    perfil_nome, perfil, divs = _analisar(rede, doc)  # reprocessar substitui a linha, agora com o perfil do contrato
    assert perfil_nome == nome
    assert perfil["extras_max_dia_min"] == {"valor": 300, "base_legal": "ACT de teste"}
    assert perfil["jornada_diaria_min"]["valor"] == 480 and "vigencias" in perfil["jornada_semanal_min"]  # herdados
    assert "horas_extras_acima_limite" not in [d["tipo"] for d in divs]
    assert "ACT de teste" in rede["corpos"]["gemini"][-1]["contents"][0]["parts"][0]["text"]  # o Gemini recebe o efetivo
    api = client.get(f"/documentos/{doc}/analise-ponto").json()
    assert api["perfil_nome"] == nome and api["perfil"]["extras_max_dia_min"]["valor"] == 300
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert conn.execute("SELECT count(*) FROM analise_ponto WHERE documento_id = %s", (doc,)).fetchone()[0] == 1


def test_perfil_do_contrato_mantem_44h_depois_da_ec_141(rede, nome, doc_do_contrato):  # noqa: F811
    """Contrato com a administração pública (EC 141/2026, art. 9º): sem regra automática, vale o perfil do contrato."""
    contrato, doc = doc_do_contrato
    semana = [{"data": f"2026-12-{d:02d}", "pares": [["08:00", "12:00"], ["13:00", "16:20"]] if d < 27 else []}
              for d in range(21, 28)]  # 6 x 7h20 = 44h, domingo livre, já depois de 16/12/2026
    _, _, divs = _analisar(rede, doc, semana)
    assert {d["tipo"] for d in divs} == {"semana_acima_limite", "descanso_semanal_ausente"}  # clt_padrao: 42h e 2 dias
    assert _gravar(nome, _p("jornada_semanal_min", 2640, base_legal="CF art. 7º, XIII; EC 141/2026, art. 9º"),
                   _p("repouso_semanal_dias", 0, base_legal="CLT art. 67; EC 141/2026, art. 9º")).status_code == 200
    assert client.put(f"/contratos/{contrato}/perfil-jornada", json={"perfil": nome}).status_code == 200
    perfil_nome, _, divs = _analisar(rede, doc, semana)
    assert perfil_nome == nome and divs == []


def test_lote_sem_contrato_usa_o_padrao(rede):  # noqa: F811
    lote, doc = _doc()
    try:
        perfil_nome, perfil, _ = _analisar(rede, doc)
        with psycopg.connect(config.DATABASE_URL) as conn:
            assert perfil_nome == PERFIL_PADRAO and perfil == carregar_perfil(conn)
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))
