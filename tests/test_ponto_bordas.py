"""Bordas das regras legais da folha de ponto (auditoria do Goal 6). Funções puras, sem banco nem rede.

Cada teste cita o artigo que a regra aplica; os textos foram conferidos no Planalto (CF e CLT) e na
Portaria MTP 671/2021 compilada. Todas as contas ficam no código.
"""
import pytest

from app.ponto import apurar_folha, detectar_ponto_britanico, resumir_contagens
from tests.test_ponto import CONTRATO, PERFIL, dia, regular, tipos


def _noite(data, entrada, saida):
    """Jornada noturna de par único, com o intervalo pré-assinalado (CLT art. 74, § 2º)."""
    return apurar_folha([dia(data, (entrada, saida))], PERFIL, intervalo_pre_assinalado=True)


# ------------------------------------------------------------------ marcação que atravessa a meia-noite

def test_dois_pares_com_o_segundo_depois_da_meia_noite():
    r = apurar_folha([dia("2025-11-03", ("22:00", "02:00+1"), ("03:00+1", "06:00+1"))], PERFIL)
    d = r["dias"][0]
    assert r["divergencias"] == []
    assert (d["data"], d["trabalhado_min"], d["intervalo_min"]) == ("2025-11-03", 420, 60)
    assert d["noturno_real_min"] == 360  # 22h-2h e 3h-5h: o horário noturno acaba às 5h (CLT art. 73, § 2º)
    assert d["prorrogacao_noturna_min"] == 60  # das 5h às 6h: prorrogação da jornada noturna (art. 73, § 5º)


def test_saida_depois_da_meia_noite_sem_o_marcador_e_invalida_e_nao_vira_jornada():
    r = apurar_folha([dia("2025-11-03", ("22:00", "02:00"))], PERFIL)
    assert tipos(r) == [("marcacao_invalida", "2025-11-03", None)] and r["dias"] == []


def test_jornada_que_vira_o_dia_conta_na_semana_em_que_comecou():
    # domingo 09/11 22h até segunda 10/11 5h: pertence à semana iniciada em 03/11
    folha = [regular(f"2025-11-{d:02d}") for d in range(3, 8)] + [dia("2025-11-09", ("19:00", "00:01+1"))]
    r = apurar_folha(folha, PERFIL, intervalo_pre_assinalado=True)
    semanas = [t for t in tipos(r) if t[0] == "semana_acima_limite"]
    assert [t[1] for t in semanas] == ["2025-11-03"]


# ------------------------------------------------------------------ hora noturna reduzida e jornada mista

def test_sete_horas_de_relogio_a_noite_valem_oito_horas_computadas():
    r = _noite("2025-11-03", "22:00", "05:00+1")  # CLT art. 73, § 1º: 420 / 52,5 * 60 = 480
    d = r["dias"][0]
    assert (d["trabalhado_min"], d["noturno_real_min"], d["noturno_computado_min"]) == (420, 420, 480)
    assert d["jornada_computada_min"] == 480 and d["extras_min"] == 0 and r["divergencias"] == []


def test_hora_noturna_reduzida_gera_hora_extra_que_o_relogio_nao_mostra():
    r = _noite("2025-11-03", "21:00", "05:00+1")  # 1h diurna + 7h noturnas = 60 + 480 computados
    d = r["dias"][0]
    assert d["trabalhado_min"] == 480 and d["jornada_computada_min"] == 540
    assert d["extras_min"] == 60 and r["totais"]["jornada_computada_min"] == 540


def test_jornada_mista_reduz_so_a_parte_noturna():
    r = apurar_folha([dia("2025-11-03", ("18:00", "22:00"), ("23:00", "02:00+1"))], PERFIL)  # art. 73, § 4º
    d = r["dias"][0]
    assert d["trabalhado_min"] == 420 and d["noturno_real_min"] == 180
    assert d["noturno_computado_min"] == pytest.approx(205.71)
    assert d["jornada_computada_min"] == pytest.approx(240 + 205.71) and d["extras_min"] == 0


def test_jornada_diurna_nao_muda_com_a_hora_noturna():
    d = apurar_folha([regular("2025-11-04")], PERFIL)["dias"][0]
    assert d["noturno_real_min"] == 0 and d["jornada_computada_min"] == d["trabalhado_min"] == 480


@pytest.mark.parametrize("saida,div", [
    # Jornada integralmente noturna (22h-5h = 480 computados): o que passa das 5h é prorrogação e também conta com a
    # hora de 52min30s (CLT art. 73, § 5º). 105 min reais = 120 computados: 2h extras exatas.
    ("06:45+1", []),
    ("06:46+1", [("horas_extras_acima_limite", "2025-11-03", 1.14)]),  # CLT art. 59, caput
    ("07:00+1", [("horas_extras_acima_limite", "2025-11-03", 17.14)]),
])
def test_limite_de_duas_horas_extras_com_hora_noturna(saida, div):
    assert tipos(_noite("2025-11-03", "22:00", saida)) == div


def test_semana_noturna_passa_da_duracao_semanal_pela_hora_reduzida():
    folha = [dia(f"2025-11-{d:02d}", ("22:00", "05:00+1")) for d in range(3, 9)]  # 6 noites de 7h de relógio
    r = apurar_folha(folha, PERFIL, intervalo_pre_assinalado=True)
    assert r["totais"]["trabalhado_min"] == 2520 and r["totais"]["jornada_computada_min"] == 2880
    assert tipos(r) == [("semana_acima_limite", "2025-11-03", 240)]


@pytest.mark.parametrize("declarado,diverge", [(420, None), (480, None), (450, 30)])
def test_total_declarado_aceita_relogio_ou_hora_noturna_reduzida(declarado, diverge):
    r = apurar_folha([dia("2025-11-03", ("22:00", "05:00+1"))], PERFIL, intervalo_pre_assinalado=True,
                     totais_declarados={"total_horas_min": declarado})
    assert [d["minutos"] for d in r["divergencias"]] == ([diverge] if diverge else [])


# ------------------------------------------------------------------ tolerância (CLT art. 58, § 1º)

@pytest.mark.parametrize("entrada,saida,extras", [
    ("07:55", "17:05", 0),    # 5 min em duas marcações: exatamente 10 min no dia
    ("07:55", "17:06", 11),   # 1 min acima nas duas réguas: conta o excesso inteiro
    ("07:56", "17:06", 10),   # 10 min no dia, mas uma marcação com 6 min: conta
    ("08:05", "17:00", 0),    # atraso não vira hora extra
])
def test_tolerancia_por_marcacao_e_no_dia_juntas(entrada, saida, extras):
    r = apurar_folha([dia("2025-11-04", (entrada, "12:00"), ("13:00", saida))], PERFIL, horario_contratual=CONTRATO)
    assert r["dias"][0]["extras_min"] == extras


def test_quatro_variacoes_de_cinco_minutos_passam_de_dez_no_dia():
    r = apurar_folha([dia("2025-11-04", ("07:55", "12:05"), ("12:55", "17:05"))], PERFIL, horario_contratual=CONTRATO)
    assert r["dias"][0]["extras_min"] == 20


def test_tolerancia_nao_esconde_o_limite_de_duas_horas():
    # 2h10 a mais: a tolerância não desconta nada depois de ultrapassada
    r = apurar_folha([dia("2025-11-04", ("08:00", "12:00"), ("13:00", "19:10"))], PERFIL)
    assert tipos(r) == [("horas_extras_acima_limite", "2025-11-04", 10)]


# ------------------------------------------------------------------ interjornada (CLT art. 66)

@pytest.mark.parametrize("vespera,seguinte", [("2025-10-31", "2025-11-01"), ("2025-12-31", "2026-01-01"),
                                              ("2024-02-29", "2024-03-01")])
def test_interjornada_na_virada_de_mes_e_de_ano(vespera, seguinte):
    def folha(entrada):
        return [dia(vespera, ("13:00", "17:00"), ("18:00", "22:00")), dia(seguinte, (entrada, "12:00"))]
    assert apurar_folha(folha("09:00"), PERFIL)["divergencias"] == []          # 11h exatas
    assert tipos(apurar_folha(folha("08:59"), PERFIL)) == [("interjornada_insuficiente", seguinte, 1)]


def test_interjornada_depois_de_saida_apos_a_meia_noite():
    def folha(entrada):
        return [dia("2025-10-31", ("15:30", "19:30"), ("20:30", "00:30+1")), dia("2025-11-01", (entrada, "15:00"))]
    assert apurar_folha(folha("11:30"), PERFIL)["divergencias"] == []
    assert tipos(apurar_folha(folha("11:29"), PERFIL)) == [("interjornada_insuficiente", "2025-11-01", 1)]


def test_interjornada_nao_conclui_com_dia_faltando_nem_com_folga_no_meio():
    vespera = dia("2025-11-03", ("13:00", "17:00"), ("18:00", "22:00"))
    cedo = dia("2025-11-05", ("05:00", "09:00"))
    assert apurar_folha([vespera, cedo], PERFIL)["divergencias"] == []                      # dia 04 fora da folha
    assert apurar_folha([vespera, dia("2025-11-04"), cedo], PERFIL)["divergencias"] == []   # dia 04 de folga


# ------------------------------------------------------------------ intrajornada (CLT art. 71)

@pytest.mark.parametrize("pares,falta,base", [
    ((("08:00", "12:00"),), None, None),                              # 4h exatas: sem intervalo obrigatório
    ((("08:00", "12:01"),), 15, "curto"),                             # 4h01 sem intervalo: faltam 15 (§ 1º)
    ((("08:00", "10:00"), ("10:15", "12:16")), None, None),           # 4h01 com 15 min
    ((("08:00", "10:00"), ("10:14", "12:15")), 1, "curto"),           # 4h01 com 14 min
    ((("08:00", "11:00"), ("11:15", "14:15")), None, None),           # 6h exatas com 15 min: ainda a faixa curta
    ((("08:00", "11:00"), ("11:15", "14:16")), 45, "longo"),          # 6h01 com 15 min: passa a exigir 1h (caput)
    ((("08:00", "11:00"), ("12:00", "15:01")), None, None),           # 6h01 com 1h
    ((("08:00", "11:00"), ("11:59", "15:00")), 1, "longo"),           # 6h01 com 59 min
])
def test_intervalo_intrajornada_nos_limites_de_4h_e_6h(pares, falta, base):
    r = apurar_folha([dia("2025-11-04", *pares)], PERFIL)
    ints = [d for d in r["divergencias"] if d["tipo"] == "intervalo_intrajornada_insuficiente"]
    assert [(d["minutos"], d["base_legal"]) for d in ints] == ([(falta, f"base intervalo_{base}_min")] if falta else [])


def test_intervalo_fracionado_vale_o_maior_e_nao_a_soma():
    # 20 + 40 min somam 1h, mas o art. 71 exige um intervalo de no mínimo 1h
    r = apurar_folha([dia("2025-11-04", ("08:00", "10:00"), ("10:20", "12:00"), ("12:40", "17:00"))], PERFIL)
    d = r["dias"][0]
    assert (d["intervalo_min"], d["maior_intervalo_min"]) == (60, 40)
    assert tipos(r) == [("intervalo_intrajornada_insuficiente", "2025-11-04", 20)]
    # um café de 15 min e um almoço de 1h: o maior intervalo atende
    ok = apurar_folha([dia("2025-11-04", ("08:00", "10:00"), ("10:15", "12:00"), ("13:00", "17:15"))], PERFIL)
    assert ok["divergencias"] == []


# ------------------------------------------------------------------ folha com dias faltando ou sem marcação

def test_folha_com_dias_faltando_e_dias_sem_marcacao():
    folha = [regular("2025-11-03"),                         # segunda
             # terça 04 não está na folha
             dia("2025-11-05"),                             # quarta sem marcação (folga, falta, atestado)
             {"data": "2025-11-06"},                        # quinta sem o campo pares
             dia("2025-11-07", ("", "")),                   # sexta com o par em branco
             regular("2025-11-10")]
    r = apurar_folha(folha, PERFIL)
    assert r["divergencias"] == []
    assert [(d["data"], d["trabalhado_min"]) for d in r["dias"]] == [
        ("2025-11-03", 480), ("2025-11-05", 0), ("2025-11-06", 0), ("2025-11-07", 0), ("2025-11-10", 480)]
    assert r["totais"]["dias_validos"] == 5 and r["totais"]["dias_invalidos"] == 0
    assert r["semanas_avaliadas_descanso"] == 0  # nenhuma semana com os 7 dias: descanso não é avaliado
    c = resumir_contagens(r, detectar_ponto_britanico(folha))
    assert c["descanso"]["semanas_completas_avaliadas"] == 0 and c["registro"]["ponto_britanico"] == "inconclusivo"


def test_folha_vazia_nao_gera_divergencia_nem_excecao():
    r = apurar_folha([], PERFIL, totais_declarados={"total_horas_min": None})
    assert r["dias"] == [] and r["divergencias"] == []
    assert r["totais"]["trabalhado_min"] == 0 and r["totais"]["jornada_computada_min"] == 0


def test_semana_com_dia_faltando_ainda_acusa_excesso_semanal_mas_nao_o_descanso():
    # 5 dias de 10h (2h extras exatas por dia) = 50h; faltam sábado e domingo na folha
    folha = [dia(f"2025-11-{d:02d}", ("08:00", "12:00"), ("13:00", "19:00")) for d in range(3, 8)]
    r = apurar_folha(folha, PERFIL)
    assert tipos(r) == [("semana_acima_limite", "2025-11-03", 360)] and r["semanas_avaliadas_descanso"] == 0
