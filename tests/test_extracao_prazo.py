from datetime import date

import pytest

from app import extracao, prompts


@pytest.mark.parametrize("inicio,n,un,esperado", [
    (date(2024, 7, 27), 45, "dias", date(2024, 9, 9)),    # o dia do início conta
    (date(2024, 1, 1), 1, "dias", date(2024, 1, 1)),
    (date(2024, 7, 27), 3, "meses", date(2024, 10, 26)),
    (date(2024, 1, 31), 1, "meses", date(2024, 2, 28)),   # fim de mês: 29/02 limitado, menos 1 dia
    (date(2023, 1, 31), 1, "meses", date(2023, 2, 27)),
    (date(2024, 11, 15), 3, "meses", date(2025, 2, 14)),  # virada de ano
    (date(2024, 12, 1), 12, "meses", date(2025, 11, 30)),
])
def test_calcular_data_termino(inicio, n, un, esperado):
    assert extracao.calcular_data_termino(inicio, n, un) == esperado


@pytest.mark.parametrize("inicio,n,un", [
    (None, 45, "dias"), (date(2024, 7, 27), None, "dias"), (date(2024, 7, 27), 45, None),
    (date(2024, 7, 27), 0, "dias"), (date(2024, 7, 27), -3, "meses"), (date(2024, 7, 27), "45", "dias"),
    (date(2024, 7, 27), True, "dias"), (date(2024, 7, 27), 45, "anos"),
])
def test_prazo_ausente_ou_invalido_nao_calcula(inicio, n, un):
    assert extracao.calcular_data_termino(inicio, n, un) is None


def test_limpar_calcula_termino_da_resposta_do_gemini():
    r = {"data_admissao": "2024-07-27", "tipo_prazo": "determinado", "prazo_numero": 45, "prazo_unidade": "dias"}
    saida = extracao.limpar(r)
    assert saida["data_termino"] == "2024-09-09"
    assert "prazo_numero" not in saida and "prazo_unidade" not in saida


def test_limpar_data_explicita_prevalece():
    r = {"data_admissao": "2024-07-27", "data_termino": "31/12/2024", "prazo_numero": 45, "prazo_unidade": "dias"}
    assert extracao.limpar(r)["data_termino"] == "2024-12-31"


def test_limpar_sem_inicio_ou_sem_prazo_nao_inventa_termino():
    assert "data_termino" not in extracao.limpar({"prazo_numero": 45, "prazo_unidade": "dias"})
    assert "data_termino" not in extracao.limpar({"data_admissao": "2024-07-27"})
    assert "data_termino" not in extracao.limpar({"data_admissao": "2024-07-27", "prazo_numero": 45, "prazo_unidade": "x"})


def test_schema_e_prompt_pedem_o_prazo():
    props = prompts.SCHEMA_EXTRACAO["properties"]
    assert props["prazo_numero"]["type"] == "INTEGER" and props["prazo_unidade"]["enum"] == ["dias", "meses"]
    assert "prazo_numero" in prompts.prompt_extracao("contrato_trabalho", "x")
