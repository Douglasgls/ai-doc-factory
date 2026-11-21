"""Score de conformidade da empresa: funções puras, datas e valores fixos."""
from datetime import date

import pytest

from app import config, conformidade
from app.conformidade import (agrupar_empresas, calcular_empresa, classificar_score, identificar_empresa,
                              normalizar, score_inteiro, validar_cnpj, validar_cpf)

REF = date(2025, 6, 1)
CNPJ_A, CNPJ_B = "11222333000181", "11444777000161"
CPF1, CPF2 = "52998224725", "11144477735"
OBRIG = ["aso", "contrato_trabalho", "holerite", "folha_pagamento", "folha_ponto"]


def pessoa(cnpj=CNPJ_A, cpf=CPF1, nome="Maria da Silva", **extra):
    return {"cnpj_prestadora": cnpj, "razao_social_prestadora": "Alfa Serviços Ltda", "distingue_prestadora": "true",
            "nome": nome, "cpf": cpf, "matricula": "0042", "data_admissao": "2024-02-01",
            "data_exame": "2025-03-01", "data_termino": "2026-01-01", "tipo_prazo": "determinado", **extra}


def lote(tipos, campos_base, primeiro_id=1, lote_id=1, estado="classificado"):
    docs = [{"id": primeiro_id + i, "lote_id": lote_id, "tipo": t, "estado": estado} for i, t in enumerate(tipos)]
    return docs, {d["id"]: dict(campos_base) for d in docs}


def avaliar(docs, campos, cnpj=CNPJ_A, ref=REF):
    empresas, _ = agrupar_empresas(docs, campos)
    return calcular_empresa(empresas[cnpj], campos, ref)


def fecha_em_100(r):
    return abs(r["score_bruto"] + sum(d["pontos"] for d in r["descontos"]) - 100) <= \
        conformidade.TOLERANCIA_ARREDONDAMENTO * (len(r["descontos"]) + 1)


def test_config_valida_contra_tipos():
    assert set(conformidade.OBRIGATORIOS) <= set(config.TIPOS) and set(conformidade.VALIDADE) <= set(config.TIPOS)
    assert sum(conformidade.PESOS.values()) == 100


def test_validacao_de_cnpj_e_cpf():
    assert validar_cnpj("11.222.333/0001-81") == CNPJ_A and validar_cnpj(CNPJ_B) == CNPJ_B
    assert validar_cnpj("11222333000182") is None and validar_cnpj("00000000000000") is None
    assert validar_cnpj("123") is None and validar_cnpj(None) is None
    assert validar_cpf("529.982.247-25") == CPF1 and validar_cpf("52998224726") is None
    assert validar_cpf("11111111111") is None


def test_identificacao_da_empresa():
    assert identificar_empresa(pessoa()) == (CNPJ_A, None)
    assert identificar_empresa(pessoa(cnpj="11.222.333/0001-81"))[0] == CNPJ_A
    assert identificar_empresa(pessoa(cnpj=""))[0] is None
    assert identificar_empresa(pessoa(cnpj="11222333000182")) == (None, "CNPJ da prestadora inválido")
    assert identificar_empresa(pessoa(distingue_prestadora="false"))[0] is None


def test_dois_cnpjs_ficam_separados_e_documento_sem_empresa_e_listado():
    da, ca = lote(OBRIG, pessoa())
    db, cb = lote(OBRIG, pessoa(cnpj=CNPJ_B, cpf=CPF2), primeiro_id=10)
    dx, cx = lote(["holerite", "aso"], pessoa(cnpj="11222333000182"), primeiro_id=20)  # CNPJ inválido
    dn, _ = lote(["holerite"], {}, primeiro_id=30, estado="em_revisao")
    docs, campos = da + db + dx + dn, {**ca, **cb, **cx}
    empresas, sem = agrupar_empresas(docs, campos)
    assert {c: len(v) for c, v in empresas.items()} == {CNPJ_A: 5, CNPJ_B: 5}
    assert {(s["id"], s["motivo"]) for s in sem if s["id"] in (20, 21)} == {
        (20, "CNPJ da prestadora inválido"), (21, "CNPJ da prestadora inválido")}
    assert [s["id"] for s in sem if s["id"] == 30] == [30] and sem[-1]["motivo"] == "CNPJ da prestadora ausente"  # em_revisao sem CNPJ


def test_empresa_completa_tem_100_nos_tres_niveis():
    docs, campos = lote(OBRIG, pessoa())
    r = avaliar(docs, campos)
    assert (r["geral"]["score"], r["geral"]["classificacao"], r["geral"]["provisorio"]) == (100, "Regular", False)
    assert r["razao_social"] == "Alfa Serviços Ltda" and r["data_referencia"] == "2025-06-01"
    assert all(r["por_tipo"][t]["score"] == 100 for t in OBRIG)
    assert all(v["score"] == 100 for v in r["por_documento"].values())
    assert r["por_documento"][1]["criterios"]["completude"]["aplicavel"] is False


@pytest.mark.parametrize("score,faixa", [(100, "Regular"), (85, "Regular"), (84, "Atenção"), (65, "Atenção"),
                                         (64, "Crítico"), (0, "Crítico")])
def test_limites_de_faixa(score, faixa):
    assert classificar_score(score) == faixa


def test_arredondamento_antes_de_classificar():
    assert classificar_score(score_inteiro(84.5)) == "Regular" and classificar_score(score_inteiro(84.49)) == "Atenção"
    assert classificar_score(score_inteiro(64.5)) == "Atenção" and classificar_score(score_inteiro(64.49)) == "Crítico"


def test_obrigatorio_ausente_sem_documento_nao_identificado():
    docs, campos = lote([t for t in OBRIG if t != "folha_ponto"], pessoa())
    g = avaliar(docs, campos)["geral"]
    assert [(d["criterio"], d["tipo"], d["regra"], d["pontos"]) for d in g["descontos"]] == [
        ("completude", "folha_ponto", "obrigatorio_ausente", 8.0)]
    assert (g["score"], g["classificacao"], g["provisorio"]) == (92, "Regular", False) and fecha_em_100(g)


def test_desconhecido_da_propria_empresa_torna_os_faltantes_pendentes():
    docs, campos = lote([t for t in OBRIG if t not in ("folha_ponto", "aso")], pessoa())
    nao, cn = lote(["desconhecido"], pessoa(), primeiro_id=50, estado="em_revisao")
    g = avaliar(docs + nao, {**campos, **cn})["geral"]
    assert g["descontos"] == [] and g["score"] == 100 and g["provisorio"] is True
    assert {p["tipo"] for p in g["pendencias"] if p["criterio"] == "completude"} == {"folha_ponto", "aso"}


def test_em_revisao_com_tipo_sugerido_cobre_so_esse_tipo():
    docs, campos = lote([t for t in OBRIG if t not in ("folha_ponto", "aso")], pessoa())
    nao, cn = lote(["folha_ponto"], pessoa(), primeiro_id=50, estado="em_revisao")
    g = avaliar(docs + nao, {**campos, **cn})["geral"]
    assert [d["tipo"] for d in g["descontos"]] == ["aso"]  # aso é ausente; folha_ponto é pendente
    assert [p["tipo"] for p in g["pendencias"] if p["criterio"] == "completude"] == ["folha_ponto"]
    assert g["provisorio"] is True and g["score"] == 90


def _por_tipo_com_revisao(tipo_revisao):
    docs, campos = lote(OBRIG, pessoa())
    nao, cn = lote([tipo_revisao], pessoa(), primeiro_id=50, estado="em_revisao")
    base = avaliar(docs, campos)["por_tipo"]
    return base, avaliar(docs + nao, {**campos, **cn})["por_tipo"]


def test_por_tipo_com_doc_do_mesmo_tipo_em_revisao_fica_provisorio_com_pendencia():
    base, r = _por_tipo_com_revisao("holerite")
    h = r["holerite"]
    assert base["holerite"]["provisorio"] is False and h["provisorio"] is True
    assert [(p["documento"], p["tipo"]) for p in h["pendencias"]] == [(50, "holerite")]
    assert "não analisado" in h["pendencias"][0]["motivo"]
    assert (h["score"], h["score_bruto"]) == (base["holerite"]["score"], base["holerite"]["score_bruto"])  # pendente nunca vale zero


def test_por_tipo_em_revisao_desconhecido_torna_qualquer_tipo_provisorio():
    base, r = _por_tipo_com_revisao("desconhecido")
    for t in OBRIG:
        assert r[t]["provisorio"] is True and r[t]["score"] == base[t]["score"]
        assert [p["documento"] for p in r[t]["pendencias"]] == [50]


def test_por_tipo_em_revisao_de_outro_tipo_conhecido_nao_torna_provisorio():
    base, r = _por_tipo_com_revisao("holerite")
    for t in OBRIG:
        if t != "holerite":
            assert r[t]["provisorio"] is False and r[t]["pendencias"] == []
            assert r[t]["score"] == base[t]["score"]


def test_pendente_em_uma_empresa_nao_blinda_a_outra_nem_documento_sem_empresa_afeta():
    da, ca = lote([t for t in OBRIG if t != "folha_ponto"], pessoa())
    db, cb = lote([t for t in OBRIG if t != "folha_ponto"], pessoa(cnpj=CNPJ_B, cpf=CPF2), primeiro_id=10)
    pend, cp = lote(["desconhecido"], pessoa(), primeiro_id=50, estado="em_revisao")  # pendente em A
    sem, cs = lote(["folha_ponto"], pessoa(cnpj=""), primeiro_id=60)  # sem empresa, mesmo lote
    docs, campos = da + db + pend + sem, {**ca, **cb, **cp, **cs}
    a, b = avaliar(docs, campos), avaliar(docs, campos, cnpj=CNPJ_B)
    assert a["geral"]["descontos"] == [] and a["geral"]["provisorio"] is True
    assert [d["tipo"] for d in b["geral"]["descontos"]] == ["folha_ponto"] and b["geral"]["provisorio"] is False
    assert b["geral"]["score"] == 92
    assert {s["id"] for s in agrupar_empresas(docs, campos)[1]} == {60}


def test_empresa_so_com_recibo_ferias_tem_score_baixo():
    docs, campos = lote(["recibo_ferias"], pessoa())
    g = avaliar(docs, campos)["geral"]
    assert g["criterios"]["completude"]["nota"] == 0.0 and len(g["descontos"]) == 5
    assert g["score"] == 0 and g["classificacao"] == "Crítico" and fecha_em_100(g)


def test_aso_vencido_nos_tres_niveis():
    docs, campos = lote(OBRIG, pessoa())
    campos[1]["data_exame"] = "2024-03-01"  # vence 2025-03-01
    r = avaliar(docs, campos)
    d = r["geral"]["descontos"]
    assert len(d) == 1 and (d[0]["criterio"], d[0]["tipo"], d[0]["documento"], d[0]["regra"]) == (
        "validade", "aso", 1, "documento_vencido") and "2025-03-01" in d[0]["detalhe"]
    assert d[0]["pontos"] == 17.5 and r["geral"]["score"] == 83 and fecha_em_100(r["geral"])
    assert r["por_tipo"]["aso"]["criterios"]["validade"]["nota"] == 0.0
    assert r["por_documento"][1]["criterios"]["validade"]["nota"] == 0.0
    assert r["por_documento"][1]["score"] < 100 and r["por_tipo"]["holerite"]["score"] == 100
    assert r["por_documento"][3]["criterios"]["validade"]["aplicavel"] is False  # holerite


def test_vencer_hoje_ainda_vale():
    docs, campos = lote(OBRIG, pessoa())
    campos[1]["data_exame"] = "2024-06-01"  # vence em 2025-06-01
    assert avaliar(docs, campos)["geral"]["descontos"] == []
    amanha = avaliar(docs, campos, ref=date(2025, 6, 2))["geral"]["descontos"]
    assert [x["regra"] for x in amanha] == ["documento_vencido"]


def test_contrato_indeterminado_nao_se_aplica():
    docs, campos = lote(OBRIG, pessoa())
    campos[2].update(tipo_prazo="indeterminado", data_termino="")
    r = avaliar(docs, campos)
    assert r["geral"]["criterios"]["validade"]["bons"] == 1 and r["geral"]["pendencias"] == []
    c = r["por_documento"][2]["criterios"]["validade"]
    assert c["aplicavel"] is False
    assert c["pendente"] is False and c["nota"] is None
    assert not any(p["criterio"] == "validade" for p in r["geral"]["pendencias"])
    # determinado sem data fica pendente (não zera)
    campos[2].update(tipo_prazo="determinado")
    r = avaliar(docs, campos)
    assert any(p["criterio"] == "validade" and p["documento"] == 2 for p in r["geral"]["pendencias"])
    assert r["geral"]["descontos"] == [] and r["geral"]["provisorio"] is False  # campo ausente não é provisório


def test_cpfs_diferentes_nao_divergem_e_mesmo_cpf_com_nome_divergente_sim():
    da, ca = lote(OBRIG, pessoa())
    db, cb = lote(["holerite", "aso"], pessoa(cpf=CPF2, nome="João Pereira", matricula="77"), primeiro_id=10)
    docs, campos = da + db, {**ca, **cb}
    assert avaliar(docs, campos)["geral"]["descontos"] == []  # pessoas diferentes: nada a comparar entre elas
    campos[3]["nome"] = "Mario da Silva"  # holerite da Maria, mesmo CPF
    g = avaliar(docs, campos)["geral"]
    nome = [d for d in g["descontos"] if d["campo"] == "nome"]
    assert len(nome) == 1 and nome[0]["cpf"] == CPF1 and nome[0]["conferir"] is True
    assert {"documento": 3, "tipo": "holerite", "valor": "Mario da Silva"} in nome[0]["valores"]
    assert {v["documento"] for v in nome[0]["valores"]} <= {1, 2, 3, 5}  # nunca documentos de outro CPF
    assert fecha_em_100(g) and g["score"] < 100


def test_razao_social_divergente_na_empresa():
    docs, campos = lote(OBRIG, pessoa())
    campos[4]["razao_social_prestadora"] = "Beta Comércio SA"
    g = avaliar(docs, campos)["geral"]
    assert [(d["criterio"], d["campo"]) for d in g["descontos"]] == [("consistencia", "razao_social_prestadora")]


def test_normalizacao_nome_e_cpf_formatado():
    docs, campos = lote(OBRIG, pessoa())
    campos[3]["nome"] = "  MARÍA   da silva. "
    campos[1]["cpf"] = "529.982.247-25"
    assert avaliar(docs, campos)["geral"]["descontos"] == []
    assert normalizar("data_admissao", "01/02/2024") == normalizar("data_admissao", "2024-02-01")


def test_cpf_ausente_ou_invalido_tira_o_documento_da_comparacao_com_pendencia():
    docs, campos = lote(OBRIG, pessoa())
    campos[3]["cpf"] = "52998224726"
    campos[3]["nome"] = "Outra Pessoa"  # sem CPF válido não é comparado com ninguém
    g = avaliar(docs, campos)["geral"]
    assert g["descontos"] == [] and g["provisorio"] is False
    assert {"criterio": "consistencia", "documento": 3, "tipo": "holerite",
            "motivo": "campo 'cpf' inválido"} in g["pendencias"]


def test_sem_extracao_criterios_pendentes_e_peso_redistribuido():
    docs, campos = lote(OBRIG, pessoa(data_exame="", data_termino="", nome="", cpf="", matricula="",
                                      data_admissao="", razao_social_prestadora=""))
    g = avaliar(docs, campos)["geral"]
    assert g["criterios"]["validade"]["pendente"] and g["criterios"]["consistencia"]["pendente"]
    assert g["criterios"]["completude"]["peso_efetivo"] == 100.0
    assert g["score"] == 100 and g["provisorio"] is True  # critério inteiro pendente


def test_documento_nao_analisado_nao_zera_a_nota():
    docs, campos = lote(OBRIG, pessoa())
    for tipo in ("holerite", "desconhecido"):
        extra, cx = lote([tipo], pessoa(), primeiro_id=99, estado="em_revisao")
        g = avaliar(docs + extra, {**campos, **cx})["geral"]
        assert g["score"] == 100 and g["provisorio"] is True and any(p["documento"] == 99 for p in g["pendencias"])
    for estado in ("segmentado", "erro"):  # nunca têm empresa
        extra, cx = lote(["holerite"], pessoa(), primeiro_id=98, estado=estado)
        assert 98 in {s["id"] for s in agrupar_empresas(docs + extra, {**campos, **cx})[1]}


def test_soma_dos_descontos_fecha_em_100_com_varios_descontos():
    docs, campos = lote(["aso", "holerite", "folha_ponto"], pessoa(data_exame="2020-01-01"))
    campos[2]["nome"], campos[3]["matricula"] = "Ana Souza", "9"
    g = avaliar(docs, campos)["geral"]
    assert len(g["descontos"]) == 2 + 1 + 2  # 2 ausentes, 1 vencido, nome e matrícula
    assert fecha_em_100(g)


# --- contrato do lote como fonte da empresa ------------------------------------------------------------
def com_contrato(docs, cnpj):
    return [{**d, "cnpj_contrato": cnpj} for d in docs]


def test_contrato_cnpj_igual_liga_normalmente():
    docs, campos = lote(OBRIG, pessoa())
    r = avaliar(com_contrato(docs, CNPJ_A), campos)
    assert r["geral"]["descontos"] == [] and r["geral"]["score"] == 100
    assert {v["origem_empresa"] for v in r["por_documento"].values()} == {"extraido"}


@pytest.mark.parametrize("extra", [{"cnpj": ""}, {"cnpj": "11222333000182"}, {"distingue_prestadora": "false"}])
def test_contrato_sem_cnpj_valido_liga_pelo_contrato(extra):
    docs, campos = lote(OBRIG, pessoa(**extra))
    empresas, sem = agrupar_empresas(com_contrato(docs, CNPJ_A), campos)
    assert sem == [] and len(empresas[CNPJ_A]) == 5
    r = calcular_empresa(empresas[CNPJ_A], campos, REF)
    assert {v["origem_empresa"] for v in r["por_documento"].values()} == {"contrato"}
    assert r["geral"]["descontos"] == []  # ligar pelo contrato não é divergência


def test_contrato_cnpj_diferente_liga_ao_contrato_e_desconta_consistencia():
    docs, campos = lote(OBRIG, pessoa())
    campos[3] = pessoa(cnpj=CNPJ_B)  # documento 3 traz outro CNPJ válido
    empresas, sem = agrupar_empresas(com_contrato(docs, CNPJ_A), campos)
    assert sem == [] and CNPJ_B not in empresas and len(empresas[CNPJ_A]) == 5
    r = calcular_empresa(empresas[CNPJ_A], campos, REF)
    d = [x for x in r["geral"]["descontos"] if x["regra"] == "cnpj_diferente_do_contrato"]
    assert len(d) == 1 and d[0]["criterio"] == "consistencia" and d[0]["documento"] == 3 and d[0]["pontos"] > 0
    assert d[0]["conferir"] and d[0]["cnpj_extraido"] == CNPJ_B and d[0]["cnpj_contrato"] == CNPJ_A
    assert r["por_documento"][3]["origem_empresa"] == "contrato" and r["por_documento"][3]["descontos"]
    assert r["geral"]["criterios"]["consistencia"]["nota"] < 1 and fecha_em_100(r["geral"])
    assert r["por_documento"][1]["descontos"] == []


def test_lote_sem_contrato_mantem_a_regra_antiga():
    docs, campos = lote(OBRIG, pessoa(cnpj=""))
    empresas, sem = agrupar_empresas(docs, campos)
    assert empresas == {} and {s["motivo"] for s in sem} == {"CNPJ da prestadora ausente"}
    docs, campos = lote(OBRIG, pessoa())
    empresas, _ = agrupar_empresas([{**d, "cnpj_contrato": None} for d in docs], campos)
    assert len(empresas[CNPJ_A]) == 5 and all(d["divergencia_cnpj"] is None for d in empresas[CNPJ_A])


def test_contrato_nao_liga_segmentado_nem_erro():
    docs, campos = lote(["holerite"], pessoa(cnpj=""), estado="erro")
    empresas, sem = agrupar_empresas(com_contrato(docs, CNPJ_A), campos)
    assert empresas == {} and len(sem) == 1


def test_dois_contratos_diferentes_ficam_separados():
    da, ca = lote(OBRIG, pessoa(cnpj=""))
    db, cb = lote(OBRIG, pessoa(cnpj="", cpf=CPF2), primeiro_id=10, lote_id=2)
    empresas, sem = agrupar_empresas(com_contrato(da, CNPJ_A) + com_contrato(db, CNPJ_B), {**ca, **cb})
    assert sem == [] and {c: len(v) for c, v in empresas.items()} == {CNPJ_A: 5, CNPJ_B: 5}


def test_cnpj_do_contrato_e_um_campo_por_empresa_e_nao_dilui_outras_divergencias():
    base = {"cnpj_prestadora": CNPJ_A, "distingue_prestadora": "true", "cpf": CPF1, "nome": "Maria da Silva"}
    docs, campos = lote(["holerite"] * 10, base)
    campos[4] = {**base, "nome": "Mario Souza"}  # mesmo CPF, nome divergente
    r = avaliar(com_contrato(docs, CNPJ_A), campos)
    c = r["geral"]["criterios"]["consistencia"]
    assert (c["bons"], c["ruins"], c["nota"]) == (1, 1, 0.5)  # 1 coerente (CNPJ) + 1 divergente (nome), não 10/11
    assert [d["regra"] for d in r["geral"]["descontos"] if d["criterio"] == "consistencia"] == ["campo_divergente"]


def test_cnpj_divergente_so_pune_os_documentos_divergentes():
    docs, campos = lote(OBRIG, pessoa())
    for i in (2, 3):
        campos[i] = pessoa(cnpj=CNPJ_B)
    r = avaliar(com_contrato(docs, CNPJ_A), campos)
    d = [x for x in r["geral"]["descontos"] if x["regra"] == "cnpj_diferente_do_contrato"]
    assert len(d) == 1 and "2 documento" in d[0]["detalhe"] and d[0]["documento"] is None
    assert {v["documento"] for v in d[0]["valores"]} == {2, 3} and "cnpj_extraido" not in d[0]
    assert {v["cnpj_contrato"] for v in d[0]["valores"]} == {CNPJ_A}
    assert r["por_documento"][2]["descontos"] and r["por_documento"][3]["descontos"]
    assert r["por_documento"][1]["descontos"] == []  # coerente numa empresa com divergência: não é punido
