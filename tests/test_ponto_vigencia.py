"""Vigência por data do perfil (EC 141/2026), repouso semanal de 2 dias e prorrogação noturna (CLT art. 73, § 5º).

As datas da emenda vêm do seed (migração 0006); o teste com banco confere o seed e os demais usam um perfil montado
aqui com as mesmas datas, para rodar sem Postgres."""
import copy
from datetime import date

import psycopg
import pytest

from app import config
from app.ponto import apurar_folha, carregar_perfil, detectar_ponto_britanico, montar_perfil, resumir_contagens, vigente
from tests.test_ponto import PERFIL, dia, tipos

PERFIL_EC = copy.deepcopy(PERFIL)
PERFIL_EC["jornada_semanal_min"]["vigencias"] = [
    {"desde": "2026-12-16", "valor": 2520, "base_legal": "EC 141, art. 6º, I"},
    {"desde": "2027-12-16", "valor": 2400, "base_legal": "EC 141, art. 6º, II"}]
PERFIL_EC["repouso_semanal_dias"]["vigencias"] = [
    {"desde": "2026-12-16", "valor": 2, "base_legal": "CF art. 7º, XV"}]


def _de(r, tipo):
    return [t for t in tipos(r) if t[0] == tipo]


def _semana(segunda, minutos_por_dia, trabalhados=6):
    """Semana de segunda a domingo: `trabalhados` dias seguidos com a mesma jornada (1h de intervalo) e o resto folga."""
    y, m, d = (int(x) for x in segunda.split("-"))
    assert date(y, m, d).weekday() == 0
    fim = 13 * 60 + minutos_por_dia - 240
    itens = []
    for n in range(7):
        data = date(y, m, d + n).isoformat()
        itens.append(dia(data, ("08:00", "12:00"), ("13:00", f"{fim // 60:02d}:{fim % 60:02d}")) if n < trabalhados
                     else dia(data))
    return itens


# ---------- vigência ----------

def test_seed_do_banco_traz_as_datas_da_ec_141():
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    with conn:
        perfil = carregar_perfil(conn)
    assert [(v["desde"], v["valor"]) for v in perfil["jornada_semanal_min"]["vigencias"]] == [
        ("2026-12-16", 2520.0), ("2027-12-16", 2400.0)]
    assert perfil["jornada_semanal_min"]["valor"] == 2640.0
    assert perfil["repouso_semanal_dias"]["valor"] == 0.0
    assert [(v["desde"], v["valor"]) for v in perfil["repouso_semanal_dias"]["vigencias"]] == [("2026-12-16", 2.0)]
    assert "vigencias" not in perfil["jornada_diaria_min"]
    for parametro, d, valor in (("jornada_semanal_min", date(2026, 12, 15), 2640), ("jornada_semanal_min", date(2026, 12, 16), 2520),
                                ("jornada_semanal_min", date(2027, 12, 15), 2520), ("jornada_semanal_min", date(2027, 12, 16), 2400),
                                ("repouso_semanal_dias", date(2026, 12, 15), 0), ("repouso_semanal_dias", date(2026, 12, 16), 2)):
        assert vigente(perfil, parametro, d)[0] == valor, (parametro, d)
    assert "EC 141" in vigente(perfil, "jornada_semanal_min", date(2026, 12, 16))[1]


def test_montar_perfil_ordena_vigencias_e_exige_valor_de_base():
    perfil = montar_perfil([("x", 3, "c", date(2028, 1, 1)), ("x", 1, "a", None), ("x", 2, "b", date(2027, 1, 1)),
                            ("y", 9, "d", None)])
    assert perfil == {"x": {"valor": 1.0, "base_legal": "a", "vigencias": [
        {"desde": "2027-01-01", "valor": 2.0, "base_legal": "b"}, {"desde": "2028-01-01", "valor": 3.0, "base_legal": "c"}]},
        "y": {"valor": 9.0, "base_legal": "d"}}
    assert vigente(perfil, "x", date(2026, 12, 31)) == (1.0, "a")
    assert vigente(perfil, "x", date(2027, 1, 1)) == (2.0, "b")
    assert vigente(perfil, "x", date(2030, 1, 1)) == (3.0, "c")
    with pytest.raises(ValueError):
        montar_perfil([("x", 2, "b", date(2027, 1, 1))])


@pytest.mark.parametrize("segunda,limite,excesso", [
    ("2026-12-07", 2640, None),   # semana inteira antes de 16/12/2026: 44h
    ("2026-12-14", 2520, 120),    # atravessa 16/12/2026 (quarta): vale a regra do domingo, 42h
    ("2026-12-21", 2520, 120),
    ("2027-12-06", 2520, 120),    # última semana inteira de 42h
    ("2027-12-13", 2400, 240),    # atravessa 16/12/2027 (quinta): 40h
    ("2027-12-20", 2400, 240),
])
def test_semana_usa_o_limite_vigente_no_domingo(segunda, limite, excesso):
    r = apurar_folha(_semana(segunda, 440), PERFIL_EC)  # 6 x 7h20 = 44h exatas
    (semana,) = r["semanas"]
    assert semana["limite_semanal_min"] == limite and semana["jornada_computada_min"] == 2640
    assert semana["inicio"] == segunda and date.fromisoformat(semana["regra_vigente_em"]).weekday() == 6
    assert _de(r, "semana_acima_limite") == ([("semana_acima_limite", segunda, excesso)] if excesso else [])


def test_folha_que_atravessa_a_mudanca_avalia_cada_semana_pela_sua_regra():
    folha = _semana("2026-12-07", 440) + _semana("2026-12-14", 440) + _semana("2026-12-21", 420)  # 44h, 44h, 42h
    r = apurar_folha(folha, PERFIL_EC)
    assert _de(r, "semana_acima_limite") == [("semana_acima_limite", "2026-12-14", 120)]
    (d,) = [x for x in r["divergencias"] if x["tipo"] == "semana_acima_limite"]
    assert d["base_legal"] == "EC 141, art. 6º, I" and "2026-12-20" in d["detalhe"]
    assert [s["limite_semanal_min"] for s in r["semanas"]] == [2640, 2520, 2520]


def test_perfil_sem_vigencias_nao_muda_com_a_data():
    r = apurar_folha(_semana("2027-12-20", 440), PERFIL)  # perfil que mantém 44h (ex.: perfil próprio do contrato)
    assert _de(r, "semana_acima_limite") == [] and _de(r, "descanso_semanal_ausente") == []


# ---------- repouso semanal de 2 dias ----------

def test_repouso_de_2_dias_so_a_partir_da_vigencia():
    antes = apurar_folha(_semana("2026-12-07", 420), PERFIL_EC)  # 6 dias de trabalho e domingo livre: 24h bastam
    assert _de(antes, "descanso_semanal_ausente") == []
    depois = apurar_folha(_semana("2026-12-14", 420), PERFIL_EC)  # mesma escala na semana que termina em 20/12/2026
    assert _de(depois, "descanso_semanal_ausente") == [("descanso_semanal_ausente", "2026-12-14", 1440)]
    (d,) = [x for x in depois["divergencias"] if x["tipo"] == "descanso_semanal_ausente"]
    assert d["base_legal"] == "CF art. 7º, XV" and "1 dia(s) de repouso" in d["detalhe"]


def test_repouso_de_2_dias_presente_consecutivo_ou_nao():
    assert _de(apurar_folha(_semana("2026-12-21", 480, trabalhados=5), PERFIL_EC), "descanso_semanal_ausente") == []
    folha = _semana("2026-12-21", 480, trabalhados=6)
    folha[2] = dia("2026-12-23")  # folga na quarta e no domingo: não consecutivos, a leitura literal aceita
    assert _de(apurar_folha(folha, PERFIL_EC), "descanso_semanal_ausente") == []


def test_repouso_nenhum_dia_livre_e_dia_com_fim_de_jornada_noturna_nao_conta():
    sete = _semana("2026-12-21", 480, trabalhados=7)
    assert _de(apurar_folha(sete, PERFIL_EC), "descanso_semanal_ausente") == [
        ("descanso_semanal_ausente", "2026-12-21", 2880)]
    folha = _semana("2026-12-21", 480, trabalhados=4)  # segunda a quinta
    folha[4] = dia("2026-12-25", ("22:00", "05:00+1"))  # sexta à noite: termina no sábado
    r = apurar_folha(folha, PERFIL_EC)  # sábado tem trabalho até as 5h; só o domingo é dia de repouso
    assert _de(r, "descanso_semanal_ausente") == [("descanso_semanal_ausente", "2026-12-21", 1440)]


def test_repouso_nao_conclui_em_semana_incompleta():
    r = apurar_folha(_semana("2026-12-21", 480, trabalhados=7)[:6], PERFIL_EC)
    assert _de(r, "descanso_semanal_ausente") == [] and r["semanas_avaliadas_descanso"] == 0


def test_contagens_para_o_jev_usam_nomes_neutros():
    folha = _semana("2026-12-14", 440)
    r = apurar_folha(folha, PERFIL_EC)
    c = resumir_contagens(r, detectar_ponto_britanico(folha))
    assert c["horas_extras"]["semanas_acima_do_limite_semanal"] == 1
    assert c["descanso"]["semanas_sem_descanso_semanal"] == 1 and c["descanso"]["maior_falta_de_descanso_min"] == 1440
    assert "semanas_acima_de_44h" not in c["horas_extras"] and "semanas_sem_descanso_de_24h" not in c["descanso"]


# ---------- prorrogação noturna (CLT art. 73, § 5º) ----------

def _noite(*pares):
    return apurar_folha([dia("2025-11-03", *pares)], PERFIL, intervalo_pre_assinalado=True)["dias"][0]


def test_prorrogacao_apos_jornada_integralmente_noturna():
    d = _noite(("22:00", "07:00+1"))  # 22h-5h = 8h computadas; 5h-7h é prorrogação
    assert d["noturno_real_min"] == 420 and d["noturno_computado_min"] == 480
    assert d["prorrogacao_noturna_min"] == 120 and d["prorrogacao_noturna_computada_min"] == pytest.approx(137.14)
    assert d["jornada_computada_min"] == pytest.approx(617.14) and d["extras_min"] == pytest.approx(137.14)
    assert d["trabalhado_min"] == 540  # tempo de relógio não muda


def test_prorrogacao_gera_hora_extra_acima_do_limite():
    r = apurar_folha([dia("2025-11-03", ("22:00", "07:00+1"))], PERFIL, intervalo_pre_assinalado=True)
    assert _de(r, "horas_extras_acima_limite") == [("horas_extras_acima_limite", "2025-11-03", pytest.approx(17.14))]
    assert r["totais"]["prorrogacao_noturna_min"] == 120


def test_intervalo_dentro_do_horario_noturno_nao_descaracteriza_a_jornada_noturna():
    d = _noite(("22:00", "02:00+1"), ("03:00+1", "07:00+1"))  # cobriu das 22h às 5h, com intervalo: as 2h contam
    assert d["noturno_real_min"] == 360 and d["noturno_computado_min"] == pytest.approx(411.43)
    assert d["prorrogacao_noturna_min"] == 120 and d["prorrogacao_noturna_computada_min"] == pytest.approx(137.14)
    assert d["trabalhado_min"] == 480 and d["jornada_computada_min"] == pytest.approx(548.57)
    assert d["extras_min"] == pytest.approx(68.57) and d["maior_intervalo_min"] == 60


def test_jornada_mista_que_cobre_toda_a_noite_conta_so_a_parte_depois_das_5h():
    d = _noite(("19:00", "07:00+1"))  # 12x36: 19h-22h diurno, 22h-5h noturno, 5h-7h prorrogação
    assert d["trabalhado_min"] == 720 and d["noturno_real_min"] == 420 and d["noturno_computado_min"] == 480
    assert d["prorrogacao_noturna_min"] == 120 and d["prorrogacao_noturna_computada_min"] == pytest.approx(137.14)
    assert d["jornada_computada_min"] == pytest.approx(180 + 480 + 137.14)  # as 3h entre 19h e 22h não são reduzidas


def test_retomada_depois_de_intervalo_apos_as_5h_e_emenda_da_mesma_jornada():
    """Decisão documentada em `_prorrogacao_noturna`: intervalo menor que o descanso entre jornadas (11h) não abre
    nova jornada."""
    assert _noite(("22:00", "05:00+1"), ("06:00+1", "08:00+1"))["prorrogacao_noturna_min"] == 120
    assert _noite(("22:00", "04:30+1"), ("05:30+1", "07:00+1"))["prorrogacao_noturna_min"] == 90
    # 11h ou mais de intervalo: nova jornada, não entra
    assert _noite(("22:00", "05:00+1"), ("16:00+1", "18:00+1"))["prorrogacao_noturna_min"] == 0
    assert _noite(("22:00", "05:00+1"), ("15:59+1", "18:00+1"))["prorrogacao_noturna_min"] == 121


def test_entrada_ate_as_22h_com_a_tolerancia_por_marcacao():
    assert _noite(("22:05", "06:00+1"))["prorrogacao_noturna_min"] == 60   # 5 min: dentro da tolerância
    assert _noite(("22:06", "06:00+1"))["prorrogacao_noturna_min"] == 0
    assert _noite(("21:00", "06:00+1"))["prorrogacao_noturna_min"] == 60


@pytest.mark.parametrize("pares", [
    [("22:00", "05:00+1")],                          # termina às 5h: não há prorrogação
    [("23:00", "07:00+1")],                          # começou depois das 22h: não cobriu todo o horário noturno
    [("00:00", "07:00")],
    [("04:00", "12:00")],                            # madrugada + dia: não é jornada noturna
    [("18:00", "20:00"), ("23:00", "07:00+1")],      # não estava trabalhando às 22h
    [("05:00", "13:00")],
    [("08:00", "12:00"), ("13:00", "17:00")],
])
def test_sem_prorrogacao_fora_da_condicao(pares):
    d = _noite(*pares)
    assert d["prorrogacao_noturna_min"] == 0 and d["prorrogacao_noturna_computada_min"] == 0
