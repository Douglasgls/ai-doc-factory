"""Escopo da conformidade por nível (plataforma, tomador, prestador), com usuários e tokens reais, contra o Postgres do
compose. Cada nível só calcula o score com os documentos dos lotes que enxerga (filtro na consulta SQL)."""
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from test_conformidade_api import CPF1, CPF2, campos_pessoa, novo_lote  # noqa: F401  (novo_lote é fixture)

client = TestClient(app)


def _cabecalho(orgs, nivel, vinculo_id=None):
    colunas = {"tomador": "tomador_id", "prestador": "prestador_id"}
    campos, valores = ["email", "nome", "nivel", "papel"], [f"u-{uuid.uuid4().hex}@exemplo.invalid", "U", nivel, "admin"]
    if nivel in colunas:
        campos.append(colunas[nivel])
        valores.append(vinculo_id)
    uid = orgs.db.execute(
        f"INSERT INTO usuario ({', '.join(campos)}) VALUES ({', '.join(['%s'] * len(campos))}) RETURNING id",
        valores).fetchone()[0]
    orgs._usuarios.append(uid)
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode({"sub": str(uid), "iat": agora - 5, "exp": agora + 600},
                                                    config.AUTH_SEGREDO, algorithm="HS256")}


@pytest.fixture
def cen(orgs, novo_lote, auth_real):
    """Prestador P com contratos com os tomadores A e B; prestador Q com contrato só com A."""
    orgs._usuarios = []
    ta, tb, p, q = orgs.tomador(), orgs.tomador(), orgs.prestador(), orgs.prestador()
    cnpj = {n: orgs.db.execute("SELECT cnpj FROM prestador WHERE id = %s", (i,)).fetchone()[0]
            for n, i in (("p", p), ("q", q))}

    def contrato(t, pr):
        i = orgs.db.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s) RETURNING id",
                            (t, pr)).fetchone()[0]
        orgs.registrar("contrato", i)
        return i

    def lote_do_contrato(cid, docs):
        lote, ids = novo_lote(docs)
        orgs.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (cid, lote))
        return lote, ids

    s = type("Cenario", (), {})()
    s.cnpj_p, s.cnpj_q = cnpj["p"], cnpj["q"]
    # contrato A-P: ASO em dia e holerite. Contrato B-P: ASO vencido (desconto que só B, P e a plataforma enxergam).
    s.lote_ap, s.ids_ap = lote_do_contrato(contrato(ta, p), [
        ("aso", "classificado", campos_pessoa(s.cnpj_p, CPF1)), ("holerite", "classificado", campos_pessoa(s.cnpj_p, CPF1))])
    s.lote_bp, s.ids_bp = lote_do_contrato(contrato(tb, p), [
        ("aso", "classificado", campos_pessoa(s.cnpj_p, CPF2, data_exame="2000-01-01"))])
    s.lote_aq, s.ids_aq = lote_do_contrato(contrato(ta, q), [
        ("aso", "classificado", campos_pessoa(s.cnpj_q, CPF1))])
    s.h = {"A": _cabecalho(orgs, "tomador", ta), "B": _cabecalho(orgs, "tomador", tb),
           "P": _cabecalho(orgs, "prestador", p), "Q": _cabecalho(orgs, "prestador", q),
           "plat": _cabecalho(orgs, "plataforma")}
    yield s
    orgs.db.execute("DELETE FROM usuario WHERE id = ANY(%s)", (orgs._usuarios,))


def _docs(j):
    return set(j["por_documento"])


def _ids(*listas):
    return {str(i) for lista in listas for i in lista}


def _vencido(j):
    return ("validade", "documento_vencido") in {(d["criterio"], d["regra"]) for d in j["geral"]["descontos"]}


def test_tomador_ve_o_score_so_com_os_documentos_dos_seus_contratos(cen):
    r = client.get(f"/empresas/{cen.cnpj_p}/conformidade", headers=cen.h["A"])
    assert r.status_code == 200
    ja = r.json()
    assert _docs(ja) == _ids(cen.ids_ap) and not _vencido(ja)  # o ASO vencido do contrato B-P não aparece nem pesa
    lista = {e["cnpj"]: e for e in client.get("/empresas", headers=cen.h["A"]).json()}
    assert lista[cen.cnpj_p]["documentos_por_tipo"] == {"aso": 1, "holerite": 1}
    assert lista[cen.cnpj_p]["score"] == ja["geral"]["score"]
    jb = client.get(f"/empresas/{cen.cnpj_p}/conformidade", headers=cen.h["B"]).json()
    assert _docs(jb) == _ids(cen.ids_bp) and _vencido(jb) and jb["geral"]["score"] < ja["geral"]["score"]


def test_prestador_ve_a_propria_empresa_com_os_dois_contratos_e_nao_ve_outra(cen):
    j = client.get(f"/empresas/{cen.cnpj_p}/conformidade", headers=cen.h["P"]).json()
    assert _docs(j) == _ids(cen.ids_ap, cen.ids_bp) and _vencido(j)
    assert {e["cnpj"] for e in client.get("/empresas", headers=cen.h["P"]).json()} == {cen.cnpj_p}
    assert client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["P"]).status_code == 404
    assert client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["Q"]).status_code == 200


def test_tomador_nao_ve_empresa_sem_contrato_com_ele(cen):
    assert client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["B"]).status_code == 404
    assert cen.cnpj_q not in {e["cnpj"] for e in client.get("/empresas", headers=cen.h["B"]).json()}
    assert client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["A"]).status_code == 200


def test_conformidade_do_lote_fora_do_escopo_da_404(cen):
    ok = client.get(f"/lotes/{cen.lote_ap}/conformidade", headers=cen.h["A"])
    assert ok.status_code == 200 and [e["cnpj"] for e in ok.json()["empresas"]] == [cen.cnpj_p]
    for quem, lote in (("A", cen.lote_bp), ("B", cen.lote_ap), ("Q", cen.lote_ap), ("P", cen.lote_aq)):
        r = client.get(f"/lotes/{lote}/conformidade", headers=cen.h[quem])
        inexistente = client.get("/lotes/999999999/conformidade", headers=cen.h[quem])
        assert r.status_code == 404 and r.json() == inexistente.json(), (quem, lote)


def test_plataforma_continua_vendo_tudo(cen):
    j = client.get(f"/empresas/{cen.cnpj_p}/conformidade", headers=cen.h["plat"]).json()
    assert _docs(j) == _ids(cen.ids_ap, cen.ids_bp)
    assert client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["plat"]).status_code == 200
    assert client.get(f"/lotes/{cen.lote_bp}/conformidade", headers=cen.h["plat"]).status_code == 200
