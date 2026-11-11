"""Paginação na segmentação: coerência de 'Página k de N' e só cabeçalho/rodapé."""
import pytest

from app import segmentacao
from app.segmentacao import paginacao, segmentar

HOLERITE = "HOLERITE mensal empregador Acme Ltda competência salário base desconto INSS FGTS líquido a receber"
ASO = "ATESTADO DE SAÚDE OCUPACIONAL médico coordenador exame clínico apto para a função riscos ocupacionais"


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "CLASSIFICADOR", "regras")


def iv(docs):
    return [(d.pagina_ini, d.pagina_fim, d.ambiguo) for d in docs]


def test_pagina_2_de_2_apos_documento_completo_abre_ambiguo():
    textos = [f"{HOLERITE} Página 1 de 2", f"{HOLERITE} Página 2 de 2", f"{ASO} Página 2 de 2"]
    assert iv(segmentar(textos)) == [(1, 2, False), (3, 3, True)]


def test_n_diferente_abre_ambiguo():
    textos = [f"{HOLERITE} Página 1 de 2", f"{ASO} Página 2 de 5"]
    assert iv(segmentar(textos)) == [(1, 1, False), (2, 2, True)]


def test_k_que_nao_avanca_abre_ambiguo():
    textos = [f"{HOLERITE} Página 1 de 4", f"{HOLERITE} Página 3 de 4", f"{ASO} Página 2 de 4"]
    assert iv(segmentar(textos)) == [(1, 2, False), (3, 3, True)]


def test_salto_tolerado():
    textos = [f"{HOLERITE} Página 1 de 3", f"{HOLERITE} Página 3 de 3"]
    assert iv(segmentar(textos)) == [(1, 2, False)]


def test_continuacao_normal_nao_e_ambigua():
    textos = [f"{HOLERITE} Página 1 de 3", f"{HOLERITE} Página 2 de 3", f"{HOLERITE} Página 3 de 3"]
    assert iv(segmentar(textos)) == [(1, 3, False)]


def test_documento_sem_paginacao_conhecida_continua():
    textos = [HOLERITE, f"{HOLERITE} Página 2 de 2"]
    assert iv(segmentar(textos)) == [(1, 2, False)]


def test_paginacao_ignora_frase_no_corpo():
    corpo = "\n".join(["cabeçalho", "linha a", "linha b", "conforme página 1 de 3 do contrato", "linha c",
                       "linha d", "linha e", "rodapé"])
    assert paginacao(corpo) is None
    textos = [f"{HOLERITE} Página 1 de 2", "\n".join([HOLERITE, "x1", "x2", "x3", "ver página 1 de 3 do contrato",
                                                       "x4", "x5", "x6"])]
    assert iv(segmentar(textos)) == [(1, 2, False)]


def test_cabecalho_e_rodape_continuam_valendo():
    meio = "\n".join(f"linha {i}" for i in range(10))
    assert paginacao(f"Página 2 de 3\n{meio}") == (2, 3)
    assert paginacao(f"{meio}\nEmpresa X\nPag. 3/3") == (3, 3)
    assert paginacao(f"Página 1 de 3\n{meio}\nPágina 2 de 3") == (2, 3)  # rodapé (última) vence


def test_em_branco_com_carimbo_nao_muda():
    assert segmentacao.em_branco("PROTOCOLADO")
    assert not segmentacao.em_branco("Atestado Página 1 de 1")


def test_reconciliacao_cobre_todas_as_paginas():
    textos = [f"{HOLERITE} Página 1 de 2", "", f"{HOLERITE} Página 2 de 2", f"{ASO} Página 2 de 2", "PROTOCOLADO",
              f"{ASO} Página 1 de 1"]
    docs = segmentar(textos)
    cobertas = [p for d in docs for p in range(d.pagina_ini, d.pagina_fim + 1)]
    assert cobertas == list(range(1, len(textos) + 1))
