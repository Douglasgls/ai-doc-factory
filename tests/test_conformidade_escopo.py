"""Escopo da conformidade por nível (plataforma, tomador, prestador), com usuários e tokens reais, contra o Postgres do
compose. Cada nível só calcula o score com os documentos dos lotes que enxerga (filtro na consulta SQL)."""
import time
import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app import config
from app.api import app
from conftest import cnpj_valido
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
    s.contrato, s.lote_do_contrato, s.p = contrato, lote_do_contrato, p
    s.orgs, s.ta, s.tb = orgs, ta, tb
    s.cnpj_p, s.cnpj_q = cnpj["p"], cnpj["q"]
    # contrato A-P: ASO em dia e holerite. Contrato B-P: ASO vencido (desconto que só B, P e a plataforma enxergam).
    s.novo_lote = novo_lote
    s.contrato_ap, s.contrato_bp = contrato(ta, p), contrato(tb, p)
    s.lote_ap, s.ids_ap = lote_do_contrato(s.contrato_ap, [
        ("aso", "classificado", campos_pessoa(s.cnpj_p, CPF1)), ("holerite", "classificado", campos_pessoa(s.cnpj_p, CPF1))])
    s.lote_bp, s.ids_bp = lote_do_contrato(s.contrato_bp, [
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


# ---------- regressões de escopo ----------

def _geral(cen, quem, cnpj=None):
    r = client.get(f"/empresas/{cnpj or cen.cnpj_p}/conformidade", headers=cen.h[quem])
    assert r.status_code == 200
    return r.json()


def test_pendencia_e_campo_faltando_em_outro_contrato_nao_afetam_o_tomador(cen):
    antes = _geral(cen, "A")
    cen.lote_do_contrato(cen.contrato_bp, [
        ("desconhecido", "em_revisao", campos_pessoa(cen.cnpj_p, CPF2)),
        ("holerite", "classificado", {"cnpj_prestadora": cen.cnpj_p, "distingue_prestadora": "true"})])
    depois = _geral(cen, "A")
    assert depois == antes
    assert depois["geral"]["pendencias"] == antes["geral"]["pendencias"]
    assert depois["geral"]["provisorio"] == antes["geral"]["provisorio"]
    # sanidade: quem enxerga o contrato B-P vê o efeito (a pendência de revisão)
    assert _geral(cen, "P")["geral"]["pendencias"] != antes["geral"]["pendencias"]


def test_nome_divergente_do_mesmo_cpf_em_outro_contrato_nao_desconta_o_tomador(cen):
    antes = _geral(cen, "A")
    cen.lote_do_contrato(cen.contrato_bp, [
        ("holerite", "classificado", campos_pessoa(cen.cnpj_p, CPF1, nome="Mario Souza Totalmente Outro"))])
    depois = _geral(cen, "A")
    assert depois == antes
    assert not [d for d in depois["geral"]["descontos"] if d["regra"] == "campo_divergente"]
    # sanidade: o prestador, que vê os dois contratos, enxerga a divergência
    assert [d for d in _geral(cen, "P")["geral"]["descontos"] if d["regra"] == "campo_divergente"]


def test_razao_social_de_outro_contrato_nao_muda_a_vista_pelo_tomador(cen):
    antes = _geral(cen, "A")
    assert antes["razao_social"] == "Alfa Ltda"
    extra = [("holerite", "classificado", {**campos_pessoa(cen.cnpj_p, CPF2), "razao_social_prestadora": "Beta SA"})
             for _ in range(5)]  # maioria no contrato B-P, para a razão social de P mudar se vazar
    cen.lote_do_contrato(cen.contrato_bp, extra)
    assert _geral(cen, "A")["razao_social"] == "Alfa Ltda"
    assert _geral(cen, "A") == antes
    assert _geral(cen, "P")["razao_social"] == "Beta SA"


def test_404_de_empresa_fora_do_escopo_igual_ao_de_cnpj_inexistente(cen):
    fora = client.get(f"/empresas/{cen.cnpj_q}/conformidade", headers=cen.h["B"])
    inexistente = client.get(f"/empresas/{cnpj_valido(uuid.uuid4().int)}/conformidade", headers=cen.h["B"])
    assert fora.status_code == inexistente.status_code == 404
    assert fora.json() == inexistente.json()
    assert cen.cnpj_q not in fora.text


def test_lote_sem_contrato_e_contrato_inativo_nao_alteram_o_que_o_prestador_ve(cen):
    antes = _geral(cen, "P")
    # lote sem contrato com o mesmo CNPJ de P: só a plataforma o enxerga
    novo = cen.novo_lote([("aso", "classificado", campos_pessoa(cen.cnpj_p, CPF1, data_exame="2000-01-01"))])
    # contrato B2-P inativo, com documentos que dariam desconto
    inativo = cen.orgs.db.execute(
        "INSERT INTO contrato (tomador_id, prestador_id, ativo) VALUES (%s, %s, false) RETURNING id",
        (cen.orgs.tomador(), cen.p)).fetchone()[0]
    cen.orgs.registrar("contrato", inativo)
    cen.lote_do_contrato(inativo, [("aso", "classificado", campos_pessoa(cen.cnpj_p, CPF2, data_exame="2000-01-01"))])
    assert _geral(cen, "P") == antes
    assert str(novo[1][0]) not in _geral(cen, "P")["por_documento"]
    # sanidade: a plataforma vê o lote sem contrato
    assert str(novo[1][0]) in _geral(cen, "plat")["por_documento"]
