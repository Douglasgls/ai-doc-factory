"""Cálculo de ponto: funções puras com dados fixos (a única parte com banco confere o seed do perfil)."""
import psycopg
import pytest

from app import config
from app.ponto import (apurar_folha, carregar_perfil, comparar_com_gemini, detectar_ponto_britanico,
                       score_geral)

_V = {
    "jornada_diaria_min": 480, "jornada_semanal_min": 2640, "tolerancia_marcacao_min": 5,
    "tolerancia_dia_min": 10, "extras_max_dia_min": 120, "adicional_extra_pct": 50, "interjornada_min": 660,
    "descanso_semanal_min": 1440, "intervalo_longo_acima_min": 360, "intervalo_longo_min": 60,
    "intervalo_curto_acima_min": 240, "intervalo_curto_min": 15, "noturno_inicio_min": 1320,
    "noturno_fim_min": 300, "hora_noturna_min": 52.5, "adicional_noturno_pct": 20,
    "repouso_semanal_dias": 0,  # valor de base; as vigências da EC 141/2026 estão em tests/test_ponto_vigencia.py
}
PERFIL = {k: {"valor": v, "base_legal": f"base {k}"} for k, v in _V.items()}


def dia(data, *pares):
    return {"data": data, "pares": [list(p) for p in pares]}


def regular(data):  # 8h trabalhadas, 1h de intervalo
    return dia(data, ("08:00", "12:00"), ("13:00", "17:00"))


def tipos(r):
    return [(d["tipo"], d["data"], d["minutos"]) for d in r["divergencias"]]


def test_perfil_do_banco_bate_com_o_fixture():
    with psycopg.connect(config.DATABASE_URL) as conn:
        assert {k: v["valor"] for k, v in carregar_perfil(conn).items()} == {k: float(v) for k, v in _V.items()}


def test_dia_regular_sem_divergencia():
    r = apurar_folha([regular("2025-11-04")], PERFIL)
    assert r["divergencias"] == []
    assert r["dias"][0]["trabalhado_min"] == 480 and r["dias"][0]["extras_min"] == 0


def test_folha_sintetica_do_goal():
    r = apurar_folha([dia("2025-11-03", ("08:00", "12:00"), ("12:30", "20:30")),
                      dia("2025-11-04", ("08:00", "12:00"), ("13:00", "17:00"))], PERFIL)
    d3 = r["dias"][0]
    assert d3["trabalhado_min"] == 720 and d3["extras_min"] == 240
    assert tipos(r) == [("horas_extras_acima_limite", "2025-11-03", 120),
                        ("intervalo_intrajornada_insuficiente", "2025-11-03", 30)]


@pytest.mark.parametrize("saida,extras", [("17:00", 0), ("17:10", 0), ("17:11", 11)])
def test_tolerancia_diaria_no_limite_e_acima(saida, extras):
    r = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("13:00", saida))], PERFIL)
    assert r["dias"][0]["extras_min"] == extras  # acima do limite conta o excesso inteiro


def test_tolerancia_por_marcacao_com_horario_previsto():
    previsto = {"2025-11-04": ["08:00", "12:00", "13:00", "17:00"]}
    # 6 min de atraso na saída: dentro de 10 por dia, mas acima de 5 por marcação -> conta
    r = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("13:00", "17:06"))], PERFIL, previsto)
    assert r["dias"][0]["extras_min"] == 6
    r = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("13:00", "17:05"))], PERFIL, previsto)
    assert r["dias"][0]["extras_min"] == 0


@pytest.mark.parametrize("saida,div", [("19:00", []), ("19:01", [("horas_extras_acima_limite", "2025-11-04", 1)])])
def test_duas_horas_extras_exatas_e_acima(saida, div):
    r = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("13:00", saida))], PERFIL)
    assert tipos(r) == div


def _semana(horas_sab):
    """seg-sex 8h + sábado com horas_sab (min); domingo de folga."""
    dias = [regular(f"2025-11-{d:02d}") for d in range(3, 8)]
    fim = f"{8 + horas_sab // 60:02d}:{horas_sab % 60:02d}"
    dias.append(dia("2025-11-08", ("08:00", fim)))
    dias.append(dia("2025-11-09"))
    return dias


def test_semana_de_44h_exatas_e_acima():
    assert apurar_folha(_semana(240), PERFIL)["divergencias"] == []
    r = apurar_folha(_semana(241), PERFIL)
    assert [t for t in tipos(r) if t[0] == "semana_acima_limite"] == [("semana_acima_limite", "2025-11-03", 1)]


@pytest.mark.parametrize("trab,intervalo,falta", [
    (("08:00", "12:00", "13:00", "17:00"), 60, None),         # 8h com 1h
    (("08:00", "12:00", "12:45", "16:45"), 45, 15),            # >6h com 45 min: faltam 15
    (("08:00", "11:00", "11:15", "14:15"), 15, None),          # 6h com 15 min: faixa curta ok
    (("08:00", "11:00", "11:10", "14:10"), 10, 5),             # 6h com 10 min: faltam 5
])
def test_intervalo_intrajornada_nas_duas_faixas(trab, intervalo, falta):
    r = apurar_folha([dia("2025-11-04", (trab[0], trab[1]), (trab[2], trab[3]))], PERFIL)
    assert r["dias"][0]["intervalo_min"] == intervalo
    ints = [d for d in r["divergencias"] if d["tipo"] == "intervalo_intrajornada_insuficiente"]
    assert [d["minutos"] for d in ints] == ([falta] if falta else [])


def test_intervalo_pre_assinalado_nao_gera_falso_alarme_com_par_unico():
    folha = [dia("2025-11-04", ("08:00", "17:00"))]
    sem = apurar_folha(folha, PERFIL)
    assert [d["tipo"] for d in sem["divergencias"]] == ["intervalo_intrajornada_insuficiente"]
    com = apurar_folha(folha, PERFIL, intervalo_pre_assinalado=True)
    assert com["divergencias"] == [] and com["intervalos_nao_verificados"] == ["2025-11-04"]
    assert com["intervalo_pre_assinalado"] is True
    # com dois pares o intervalo foi registrado e continua sendo verificado
    dois = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("12:30", "17:30"))], PERFIL,
                        intervalo_pre_assinalado=True)
    assert [d["minutos"] for d in dois["divergencias"]] == [30] and dois["intervalos_nao_verificados"] == []


def test_jornada_ate_4h_nao_exige_intervalo():
    assert apurar_folha([dia("2025-11-04", ("08:00", "12:00"))], PERFIL)["divergencias"] == []


def test_interjornada_de_11h_exatas_e_abaixo():
    ok = apurar_folha([dia("2025-11-03", ("08:00", "12:00"), ("13:00", "18:00")),
                       dia("2025-11-04", ("05:00", "09:00"))], PERFIL)
    assert ok["divergencias"] == []
    ruim = apurar_folha([dia("2025-11-03", ("08:00", "12:00"), ("13:00", "18:00")),
                         dia("2025-11-04", ("04:59", "08:59"))], PERFIL)
    assert tipos(ruim) == [("interjornada_insuficiente", "2025-11-04", 1)]


def test_interjornada_so_entre_dias_consecutivos():
    r = apurar_folha([dia("2025-11-03", ("08:00", "12:00"), ("13:00", "18:00")),
                      dia("2025-11-05", ("05:00", "09:00"))], PERFIL)
    assert r["divergencias"] == []


def test_descanso_semanal_ausente_e_presente():
    sete = [regular(f"2025-11-{d:02d}") for d in range(3, 10)]
    r = apurar_folha(sete, PERFIL)
    assert "descanso_semanal_ausente" in [d["tipo"] for d in r["divergencias"]]
    assert apurar_folha(_semana(0)[:5] + [dia("2025-11-08"), dia("2025-11-09")], PERFIL)["divergencias"] == []


def test_descanso_semanal_nao_conclui_com_periodo_incompleto():
    r = apurar_folha([regular(f"2025-11-{d:02d}") for d in range(3, 9)], PERFIL)  # faltam 7 dias completos
    assert "descanso_semanal_ausente" not in [d["tipo"] for d in r["divergencias"]]


def test_noturno_cruzando_a_meia_noite():
    r = apurar_folha([dia("2025-11-03", ("22:00", "02:00+1"))], PERFIL)
    d = r["dias"][0]
    assert d["noturno_real_min"] == 240 and d["noturno_computado_min"] == pytest.approx(274.29)
    r = apurar_folha([dia("2025-11-03", ("20:00", "06:00+1"))], PERFIL)
    assert r["dias"][0]["noturno_real_min"] == 420  # 22h-5h


@pytest.mark.parametrize("pares", [
    [("08:00", None)], [(None, "17:00")], [("17:00", "08:00")], [("08:00", "12:00"), ("11:00", "17:00")],
    [("8h", "17:00")],
])
def test_marcacao_invalida_vira_divergencia_e_sai_das_contas(pares):
    r = apurar_folha([dia("2025-11-03", *pares), regular("2025-11-04")], PERFIL)
    assert [d["tipo"] for d in r["divergencias"]] == ["marcacao_invalida"]
    assert r["divergencias"][0]["data"] == "2025-11-03" and r["divergencias"][0]["minutos"] is None
    assert [d["data"] for d in r["dias"]] == ["2025-11-04"]
    assert r["totais"]["dias_invalidos"] == 1


def _britanico(variacao, n):
    return [dia(f"2025-11-{d:02d}", ("08:00", "12:00"), ("13:00", f"17:{(d * variacao) % 60:02d}" if variacao else "17:00"))
            for d in range(1, n + 1)]


def test_ponto_britanico_positivo_negativo_e_poucos_dias():
    assert detectar_ponto_britanico(_britanico(0, 12))["sinal_risco"] is True
    neg = [dia(f"2025-11-{d:02d}", ("08:00", "12:00"), ("13:00", f"17:{d * 4:02d}")) for d in range(1, 12)]
    r = detectar_ponto_britanico(neg)
    assert r["conclusivo"] and r["sinal_risco"] is False and r["fracao_uniforme"] < 0.5
    poucos = detectar_ponto_britanico(_britanico(0, 5))
    assert poucos["conclusivo"] is False and poucos["sinal_risco"] is None
    assert detectar_ponto_britanico(_britanico(0, 5), min_dias=5)["sinal_risco"] is True


def test_britanico_um_dia_diferente_nao_esconde_o_mes_uniforme():
    folha = _britanico(0, 21) + [dia("2025-11-22", ("08:00", "12:00"), ("13:00", "19:30"))]
    r = detectar_ponto_britanico(folha)
    assert r["sinal_risco"] is True and r["dias"] == 22 and r["fracao_uniforme"] == pytest.approx(21 / 22, abs=1e-3)


def test_britanico_horarios_variados_nao_sinalizam():
    folha = [dia(f"2025-11-{d:02d}", (f"08:{(d * 7) % 40:02d}", "12:00"), ("13:00", f"17:{(d * 11) % 50:02d}"))
             for d in range(1, 21)]
    r = detectar_ponto_britanico(folha)
    assert r["conclusivo"] and r["sinal_risco"] is False


def test_contagens_para_o_jev_separam_falta_pequena_de_falta_maior():
    from app.ponto import resumir_contagens
    folha = [dia("2025-11-04", ("08:00", "12:00"), ("12:57", "17:57")),   # falta de 3 min
             dia("2025-11-05", ("08:00", "12:00"), ("12:30", "17:30"))]   # falta de 30 min
    ap = apurar_folha(folha, PERFIL)
    c = resumir_contagens(ap, detectar_ponto_britanico(folha))
    assert c["intervalos"]["dias_com_falta_de_intervalo_pequena"] == 1
    assert c["intervalos"]["dias_com_falta_de_intervalo_maior"] == 1 and c["intervalos"]["maior_falta_de_intervalo_min"] == 30
    assert c["registro"]["ponto_britanico"] == "inconclusivo" and c["horas_extras"]["dias_analisados"] == 2


CONTRATO = [["08:00", "12:00"], ["13:00", "17:00"]]


def test_horario_contratual_aplica_a_tolerancia_por_marcacao():
    # entrada 6 min antes do contratual: dentro de 10 min no dia, mas acima de 5 por marcação -> conta
    folha = [dia("2025-11-04", ("07:54", "12:00"), ("13:00", "17:00")), dia("2025-11-05", ("07:55", "12:00"), ("13:00", "17:00"))]
    r = apurar_folha(folha, PERFIL, horario_contratual=CONTRATO)
    assert [d["extras_min"] for d in r["dias"]] == [6, 0]  # 5 min exatos ainda é tolerado
    assert r["tolerancia_por_marcacao"] == {"aplicada": True, "dias_com_horario_previsto": 2,
                                            "dias_sem_horario_previsto": 0, "motivo_nao_aplicada": None}
    sem = apurar_folha(folha, PERFIL)  # sem horário contratual: só o teto diário
    assert [d["extras_min"] for d in sem["dias"]] == [0, 0]
    assert sem["tolerancia_por_marcacao"]["aplicada"] is False
    assert sem["tolerancia_por_marcacao"]["motivo_nao_aplicada"] == "sem_horario_contratual"


def test_horario_contratual_com_numero_de_marcacoes_diferente_mantem_so_o_teto_diario():
    folha = [dia("2025-11-04", ("07:54", "17:00")), regular("2025-11-05")]
    r = apurar_folha(folha, PERFIL, horario_contratual=CONTRATO, intervalo_pre_assinalado=True)
    t = r["tolerancia_por_marcacao"]
    assert t["dias_com_horario_previsto"] == 1 and t["dias_sem_horario_previsto"] == 1 and t["aplicada"] is True
    nada = apurar_folha([dia("2025-11-04", ("07:54", "17:00"))], PERFIL, horario_contratual=CONTRATO,
                        intervalo_pre_assinalado=True)["tolerancia_por_marcacao"]
    assert nada["aplicada"] is False and nada["motivo_nao_aplicada"] == "numero_de_marcacoes_diferente_do_horario_contratual"
    ruim = apurar_folha([regular("2025-11-04")], PERFIL, horario_contratual=[["8h", "x"]])["tolerancia_por_marcacao"]
    assert ruim["motivo_nao_aplicada"] == "horario_contratual_ilegivel"


def _folha_com_extras():
    # 04/11: 12 min de excesso (conta); 05/11: 8 min (tolerado). Bruto 20, com tolerância 12.
    return [dia("2025-11-04", ("08:00", "12:00"), ("13:00", "17:12")), dia("2025-11-05", ("08:00", "12:00"), ("13:00", "17:08"))]


def test_total_declarado_igual_ao_bruto_nao_e_divergencia_mesmo_diferindo_do_com_tolerancia():
    r = apurar_folha(_folha_com_extras(), PERFIL, totais_declarados={"total_horas_min": 980, "horas_extras_min": 20})
    t = r["totais"]
    assert (t["extras_bruto_min"], t["extras_min"]) == (20, 12)
    assert r["divergencias"] == []
    d = r["declarados"]
    assert d["extras_declarado_igual_ao_bruto"] is True and d["extras_declarado_igual_ao_com_tolerancia"] is False
    assert d["comparado"] is True


def test_total_declarado_diferente_gera_divergencia_com_campo_e_minutos():
    r = apurar_folha(_folha_com_extras(), PERFIL, totais_declarados={"total_horas_min": 1000, "horas_extras_min": 30})
    assert [(d["tipo"], d["campo"], d["minutos"], d["data"]) for d in r["divergencias"]] == [
        ("total_declarado_divergente", "total_horas", 20, None), ("total_declarado_divergente", "horas_extras", 10, None)]


def test_total_declarado_nulo_ou_ausente_nao_compara_e_tolerancia_configuravel(monkeypatch):
    for decl in ({"total_horas_min": None, "horas_extras_min": None}, None, {"horas_extras_min": "03:00"}):
        r = apurar_folha(_folha_com_extras(), PERFIL, totais_declarados=decl)
        assert r["divergencias"] == [] and r["declarados"]["comparado"] is False
    from app import ponto
    monkeypatch.setitem(ponto.CONFIG_PONTO, "total_declarado_tolerancia_min", 15)
    assert apurar_folha(_folha_com_extras(), PERFIL, totais_declarados={"horas_extras_min": 30})["divergencias"] == []


def test_total_declarado_nao_e_comparado_com_dia_invalido():
    folha = _folha_com_extras() + [dia("2025-11-06", ("08:00", None))]
    r = apurar_folha(folha, PERFIL, totais_declarados={"total_horas_min": 1, "horas_extras_min": 1})
    assert [d["tipo"] for d in r["divergencias"]] == ["marcacao_invalida"] and r["declarados"]["comparado"] is False


def test_diferenca_com_gemini_registrada_e_vale_o_codigo():
    cod = apurar_folha([dia("2025-11-03", ("08:00", "12:00"), ("12:30", "20:30"))], PERFIL)
    gem = [{"tipo": "horas_extras_acima_limite", "data": "2025-11-03", "minutos": 150},
           {"tipo": "interjornada_insuficiente", "data": "2025-11-03", "minutos": 60}]
    r = comparar_com_gemini(cod, gem)
    assert r["divergencias"] == cod["divergencias"]
    assert {(d["tipo"], d["motivo"]) for d in r["diferencas"]} == {
        ("horas_extras_acima_limite", "minutos_diferentes"),
        ("intervalo_intrajornada_insuficiente", "so_codigo"),
        ("interjornada_insuficiente", "so_gemini")}
    assert comparar_com_gemini(cod, [{"tipo": d["tipo"], "data": d["data"], "minutos": d["minutos"]}
                                     for d in cod["divergencias"]])["diferencas"] == []


def test_score_geral_e_o_maximo_das_dimensoes():
    r = score_geral({"horas_extras": {"score": 3, "n_niveis": 4, "confianca": 0.9},
                     "intervalos": {"score": 1, "n_niveis": 5, "confianca": 0.9},
                     "descanso": {"score": 0, "n_niveis": 3, "confianca": 0.9}})
    assert r["score_geral"] == 1.0 and not r["requer_revisao"]


def test_dimensao_indeterminada_nao_entra_no_maximo_e_pede_revisao():
    r = score_geral({"horas_extras": {"score": 3, "n_niveis": 4, "confianca": 0.3},
                     "intervalos": {"score": 2, "n_niveis": 5, "confianca": 0.9}})
    assert r["score_geral"] == 0.5 and r["indeterminadas"] == ["horas_extras"] and r["requer_revisao"]
    assert score_geral({"x": {"score": 1, "n_niveis": 3, "confianca": 0.1}})["score_geral"] is None
    with pytest.raises(ValueError):
        score_geral({"x": {"score": 4, "n_niveis": 4, "confianca": 0.9}})


@pytest.mark.parametrize("item", [
    {"data": "2025-11-03", "pares": [None]},
    {"data": "2025-11-03", "pares": "08001700"},
    {"data": "2025-11-03", "pares": [["08:00", "17:00", "x"]]},
    {"data": "2025-11-03", "pares": [["2025-11-03T08:00:00+00:00", "17:00"]]},   # fuso x sem fuso
    {"data": "2025-11-03", "pares": [[8, 17]]},
    {"data": None, "pares": []},
    "texto solto", None, 42, ["08:00", "17:00"],
])
def test_entrada_de_llm_malformada_vira_marcacao_invalida_sem_excecao(item):
    r = apurar_folha([item, regular("2025-11-04")], PERFIL)
    assert [d["tipo"] for d in r["divergencias"]] == ["marcacao_invalida"]
    assert [d["data"] for d in r["dias"]] == ["2025-11-04"]
    detectar_ponto_britanico([item, regular("2025-11-04")])  # também não pode levantar
