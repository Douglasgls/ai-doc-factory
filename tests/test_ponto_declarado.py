"""Totais declarados na folha: horas extras aceitam o valor bruto ou o valor com tolerância."""
from app.ponto import apurar_folha
from tests.test_ponto import PERFIL, dia


def _apurar(saida, declarado, folha=None):
    folha = folha or [dia("2025-11-04", ("08:00", "12:00"), ("13:00", saida))]
    return apurar_folha(folha, PERFIL, totais_declarados={"horas_extras_min": declarado})


def test_8h10_com_declarado_zero_nao_diverge():
    r = _apurar("17:10", 0)
    assert r["totais"]["extras_bruto_min"] == 10 and r["totais"]["extras_min"] == 0
    assert r["divergencias"] == []
    d = r["declarados"]
    assert d["comparado"] is True
    assert d["extras_declarado_igual_ao_bruto"] is False and d["extras_declarado_igual_ao_com_tolerancia"] is True


def test_declarado_igual_ao_bruto_nao_diverge():
    r = _apurar("17:10", 10)
    assert r["divergencias"] == []
    assert r["declarados"]["extras_declarado_igual_ao_bruto"] is True


def test_declarado_diferente_dos_dois_diverge_com_menor_diferenca_e_ambos_valores():
    r = _apurar("17:10", 30)  # bruto 10, com tolerância 0
    (d,) = r["divergencias"]
    assert (d["tipo"], d["campo"], d["minutos"]) == ("total_declarado_divergente", "horas_extras", 20)
    assert "10 min sem tolerância" in d["detalhe"] and "0 min com tolerância" in d["detalhe"]


def test_8h11_fora_da_tolerancia_com_declarado_zero_diverge():
    r = _apurar("17:11", 0)
    assert r["totais"]["extras_bruto_min"] == r["totais"]["extras_min"] == 11
    assert [(d["campo"], d["minutos"]) for d in r["divergencias"]] == [("horas_extras", 11)]


def test_dias_invalidos_nao_comparam():
    r = _apurar("17:10", 999, folha=[dia("2025-11-04", ("08:00", "12:00"), ("13:00", "17:10")),
                                     dia("2025-11-05", ("08:00",))])
    assert r["declarados"]["comparado"] is False
    assert [d["tipo"] for d in r["divergencias"]] == ["marcacao_invalida"]
