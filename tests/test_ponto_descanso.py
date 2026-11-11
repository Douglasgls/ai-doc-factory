"""Descanso semanal não avaliado (sem semana completa na folha) não vai ao Jev e não vira risco baixo."""
import pytest

from app import analise, prompts
from app.ponto import score_geral
from tests.test_analise import (GEM_OK_DIVS, IRREGULAR, REGULAR, _gemini, _jev, _linhas, doc, rede)  # noqa: F401

SEMANA_COMPLETA = [{"data": f"2025-11-{d:02d}", "pares": [["08:00", "12:00"], ["13:00", "17:00"]] if d < 8 else []}
                   for d in range(3, 10)]  # segunda a domingo, folga no domingo


def _pergunta_ao_jev(rede):
    assert len(rede["corpos"]["jev"]) == 1  # sempre uma única requisição
    return rede["corpos"]["jev"][0]


def test_folha_so_com_dias_uteis_nao_pergunta_descanso(doc, rede):
    rede["gemini"].append(_gemini(IRREGULAR, GEM_OK_DIVS))
    rede["jev"].append(lambda corpo: _jev(corpo, {"horas_extras": 2, "intervalos": 1, "registro": 1}))
    analise.analisar_documento({"documento_id": doc})
    jev = _pergunta_ao_jev(rede)
    assert set(jev["questions"]) == {"horas_extras", "intervalos", "registro"}
    assert "descanso" not in jev["state"]["contagens"]
    (linha,) = _linhas(doc)
    scores, geral, revisao, contagens = linha[3], linha[4], linha[5], linha[10]
    assert scores["descanso"] == {"score": None, "confianca": None, "n_niveis": None, "probabilidades": None,
                                  "normalizado": None, "indeterminada": True, "nao_avaliada": True,
                                  "motivo": "sem_semana_completa"}
    assert geral == pytest.approx(2 / 3) and revisao is False  # máximo das outras; falta de dado não força revisão
    assert contagens["nao_avaliadas"] == ["descanso"] and contagens["descanso"]["semanas_completas_avaliadas"] == 0


def test_folha_com_semana_completa_pergunta_descanso(doc, rede):
    rede["gemini"].append(_gemini(SEMANA_COMPLETA, []))
    rede["jev"].append(lambda corpo: _jev(corpo, {"descanso": 3}))
    analise.analisar_documento({"documento_id": doc})
    assert set(_pergunta_ao_jev(rede)["questions"]) == set(prompts.DIMENSOES_PONTO)
    (linha,) = _linhas(doc)
    assert linha[3]["descanso"]["nao_avaliada"] is False and linha[3]["descanso"]["normalizado"] == 1.0
    assert linha[4] == 1.0 and linha[10]["nao_avaliadas"] == []


def test_dimensao_com_confianca_baixa_continua_distinta_de_nao_avaliada(doc, rede):
    rede["gemini"].append(_gemini(REGULAR, []))
    rede["jev"].append(lambda corpo: _jev(corpo, {}, conf={"horas_extras": 0.1}))
    analise.analisar_documento({"documento_id": doc})
    (linha,) = _linhas(doc)
    assert linha[3]["horas_extras"]["indeterminada"] and not linha[3]["horas_extras"]["nao_avaliada"]
    assert linha[5] is True  # revisão por confiança baixa


def test_score_geral_todas_indeterminadas_e_descanso_nao_avaliado_e_none():
    r = score_geral({"horas_extras": {"score": 3, "n_niveis": 4, "confianca": 0.1},
                     "intervalos": {"score": 1, "n_niveis": 4, "confianca": 0.1}},
                    nao_avaliadas={"descanso": "sem_semana_completa"})
    assert r["score_geral"] is None and r["requer_revisao"] is True
    assert r["nao_avaliadas"] == ["descanso"] and r["indeterminadas"] == ["horas_extras", "intervalos"]


def test_score_geral_nao_avaliada_nao_entra_no_maximo_nem_forca_revisao():
    r = score_geral({"horas_extras": {"score": 1, "n_niveis": 4, "confianca": 0.9}},
                    nao_avaliadas={"descanso": "sem_semana_completa"})
    assert r["score_geral"] == pytest.approx(1 / 3) and not r["requer_revisao"] and r["indeterminadas"] == []
    assert r["dimensoes"]["descanso"]["nao_avaliada"] is True


def test_niveis_do_descanso_cobrem_uma_semana_avaliada_e_reprovada():
    niveis = prompts.PERGUNTAS_PONTO["descanso"]["criteria"]
    assert len(niveis) == 4 and "nenhuma semana completa pôde ser avaliada" not in " ".join(niveis)
    assert "só uma semana foi avaliada" in niveis[3]
    assert prompts.VERSAO_PROMPT_PONTO_JEV == "jev-ponto-v4"
