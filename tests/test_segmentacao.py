"""Testes puros da segmentação (sem banco): python -m pytest tests/test_segmentacao.py"""
import pytest

from app import segmentacao
from app.segmentacao import Documento, paginacao, segmentar

HOLERITE = "HOLERITE mensal empregador Acme Ltda competência salário base desconto INSS FGTS líquido a receber"
ATESTADO = "ATESTADO MÉDICO atesto que o paciente esteve em consulta CID afastamento dias médico CRM assinatura"
CONTRATO = "CONTRATO DE TRABALHO cláusula primeira jornada admissão empregado empregador contratação prazo"


def intervalos(docs):
    return [(d.pagina_ini, d.pagina_fim) for d in docs]


def test_paginacao_tolera_variacoes_de_ocr():
    assert paginacao("rodapé PÁGINA 1 DE 3") == (1, 3)
    assert paginacao("Pagina  2  de  3") == (2, 3)
    assert paginacao("Pág. 3/3") == (3, 3)
    assert paginacao("Página l de 2") == (1, 2)
    assert paginacao("sem paginação aqui") is None


def test_consecutivos_do_mesmo_tipo_com_pagina_k_de_n():
    textos = [
        f"{HOLERITE} Ana Silva Página 1 de 2", f"{HOLERITE} Ana Silva Página 2 de 2",
        f"{HOLERITE} Bruno Souza Página 1 de 2", f"{HOLERITE} Bruno Souza Página 2 de 2",
    ]
    assert intervalos(segmentar(textos)) == [(1, 2), (3, 4)]


def test_verso_em_branco_herdado():
    textos = [f"{HOLERITE} Página 1 de 1", "", f"{HOLERITE} outro Página 1 de 1", "  \n ."]
    assert intervalos(segmentar(textos)) == [(1, 2), (3, 4)]


def test_sem_paginacao_tipos_diferentes_abrem_documento(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.15)
    textos = [HOLERITE, HOLERITE + " continuação", ATESTADO, CONTRATO]
    docs = segmentar(textos)
    assert intervalos(docs) == [(1, 2), (3, 3), (4, 4)]
    assert not any(d.ambiguo for d in docs)


def test_faixa_ambigua_abre_documento_e_marca(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.0)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 1.1)
    docs = segmentar([HOLERITE, HOLERITE + " continuação"])
    assert docs == [Documento(1, 1, False), Documento(2, 2, True)]


def test_llm_pode_resolver_ambiguo(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.0)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 1.1)
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: True)
    assert intervalos(segmentar([HOLERITE, HOLERITE + " x"])) == [(1, 2)]


def test_texto_vazio_no_inicio_do_lote():
    textos = ["", "", f"{HOLERITE} Página 1 de 2", f"{HOLERITE} Página 2 de 2", f"{ATESTADO} Página 1 de 1"]
    assert intervalos(segmentar(textos)) == [(1, 4), (5, 5)]


def test_lote_so_de_paginas_vazias_e_lote_vazio():
    assert intervalos(segmentar(["", ""])) == [(1, 2)]
    assert segmentar([]) == []


def test_lote_de_uma_pagina():
    assert segmentar([HOLERITE]) == [Documento(1, 1, False)]


def test_intervalos_sem_buraco_nem_sobreposicao():
    textos = [HOLERITE, "", ATESTADO, ATESTADO + " dois", "", CONTRATO + " Página 1 de 2", CONTRATO + " Página 2 de 2", HOLERITE]
    docs = segmentar(textos)
    esperado = 1
    for d in docs:
        assert d.pagina_ini == esperado
        esperado = d.pagina_fim + 1
    assert esperado == len(textos) + 1


def test_reconciliar_detecta_buraco_e_sobreposicao():
    with pytest.raises(AssertionError):
        segmentacao.reconciliar([Documento(1, 1), Documento(3, 3)], 3)
    with pytest.raises(AssertionError):
        segmentacao.reconciliar([Documento(1, 2), Documento(2, 3)], 3)
    with pytest.raises(AssertionError):
        segmentacao.reconciliar([Documento(1, 2)], 3)


@pytest.mark.parametrize("texto,esperado", [
    ("Página i de 3", (1, 3)), ("Pagina L de 3", (1, 3)), ("Página 1 de o", None),
    ("Página 2 de |", None), ("Página | de 2", (1, 2)), ("Página 1 de |", (1, 1)),
    ("Página 0 de 3", None), ("Página 8 de 3", None), ("Página 2 de 3", (2, 3)),
])
def test_paginacao_ruido_e_valores_impossiveis(texto, esperado):
    assert paginacao(texto) == esperado


def test_segmentar_nao_lanca_com_pagina_i_de_2():
    docs = segmentar([f"{HOLERITE} Página i de 2", f"{HOLERITE} Página 2 de 2", f"{ATESTADO} Página 8 de 3"])
    assert docs[0].pagina_ini == 1 and docs[-1].pagina_fim == 3


# --- página só com carimbo, CNPJ e mesma empresa ---

def test_verso_so_com_carimbo_herda_o_documento_anterior():
    textos = [f"{HOLERITE} Página 1 de 1", "PROTOCOLADO", f"{HOLERITE} outro Página 1 de 1"]
    assert intervalos(segmentar(textos)) == [(1, 2), (3, 3)]
    assert segmentacao.em_branco("PROTOCOLADO") and segmentacao.em_branco("  \n .")


def test_carimbo_no_inicio_do_lote_e_absorvido_pelo_primeiro_documento():
    assert intervalos(segmentar(["PROTOCOLADO", f"{HOLERITE} Página 1 de 1"])) == [(1, 2)]


def test_pagina_curta_com_paginacao_ou_acima_do_limite_continua_sendo_documento():
    assert not segmentacao.em_branco("Atestado Página 1 de 1")  # paginação é conteúdo de documento
    assert not segmentacao.em_branco("ATESTADO MÉDICO ok")  # mais de 12 alfanuméricos
    textos = [f"{HOLERITE} Página 1 de 1", "Atestado Página 1 de 1"]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]


def test_limite_de_carimbo_vem_da_config(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_BRANCO_MAX_ALNUM", 0)
    assert not segmentacao.em_branco("PROTOCOLADO")


@pytest.mark.parametrize("texto,esperado", [
    ("CUNHA CNPJ 43.182.607/0001-42 Rua x", "43182607000142"),
    ("CNPJ 43182607000142", "43182607000142"),
    ("ENPJ 43.182.607/0001-42", "43182607000142"),     # rótulo mal lido
    ("CNPJ 43.182.607 /0001 - 42", "43182607000142"),  # espaços do OCR
    ("CNPJ 43,182,607/0001-42", "43182607000142"),     # vírgulas no lugar de pontos
    ("sem número, matrícula 71496 24782", None),
    ("", None),
])
def test_cnpj_tolerante(texto, esperado):
    assert segmentacao.cnpj(texto) == esperado


def _cnpj_texto(cnpj, corpo):
    return f"EMPRESA CNPJ {cnpj} {corpo}"


def _forcar_baixa_similaridade(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.99)  # toda similaridade sem paginação é "baixa"
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 1.1)


def test_mesmo_cnpj_com_similaridade_baixa_pergunta_ao_jev(monkeypatch):
    _forcar_baixa_similaridade(monkeypatch)
    perguntas = []

    def jev(a, b):
        perguntas.append((a, b))
        return True
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", jev)
    textos = [_cnpj_texto("43.182.607/0001-42", "alpha beta gama"), _cnpj_texto("43.182.607/0001-42", "delta épsilon")]
    assert intervalos(segmentar(textos)) == [(1, 2)] and len(perguntas) == 1
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: False)
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: None)  # sem resposta
    docs = segmentar(textos)
    assert intervalos(docs) == [(1, 1), (2, 2)] and docs[1].ambiguo


def test_cnpj_diferente_abre_documento_sem_perguntar(monkeypatch):
    _forcar_baixa_similaridade(monkeypatch)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.9)
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: pytest.fail("não deveria perguntar"))
    textos = [_cnpj_texto("43.182.607/0001-42", "alpha beta gama"), _cnpj_texto("54.930.781/0001-42", "alpha beta gama")]
    docs = segmentar(textos)
    assert intervalos(docs) == [(1, 1), (2, 2)] and not docs[1].ambiguo


def test_cnpj_diferente_com_paginacao_de_continuacao_continua(monkeypatch):
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: pytest.fail("não deveria perguntar"))
    textos = [_cnpj_texto("43.182.607/0001-42", "x Página 1 de 2"), _cnpj_texto("54.930.781/0001-42", "y Página 2 de 2")]
    assert intervalos(segmentar(textos)) == [(1, 2)]


def test_sem_cnpj_em_uma_das_paginas_mantem_o_comportamento_antigo(monkeypatch):
    _forcar_baixa_similaridade(monkeypatch)
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: pytest.fail("não deveria perguntar"))
    textos = [_cnpj_texto("43.182.607/0001-42", "alpha beta"), "gama delta épsilon sem empresa"]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]  # similaridade baixa, CNPJ desconhecido: abre


def test_documentos_consecutivos_da_mesma_empresa_separam_por_pagina_1_de_n_e_pelo_jev(monkeypatch):
    _forcar_baixa_similaridade(monkeypatch)
    c = "43.182.607/0001-42"
    por_paginacao = [_cnpj_texto(c, "folha Página 1 de 2"), _cnpj_texto(c, "folha Página 2 de 2"),
                     _cnpj_texto(c, "folha Página 1 de 1")]
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: pytest.fail("paginação decide"))
    assert intervalos(segmentar(por_paginacao)) == [(1, 2), (3, 3)]
    sem_paginacao = [_cnpj_texto(c, "recibo de férias gozo"), _cnpj_texto(c, "atestado médico cid repouso")]
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: False)  # o Jev separa
    assert intervalos(segmentar(sem_paginacao)) == [(1, 1), (2, 2)]


# --- CNPJs válidos pelos dígitos verificadores decidem mesmo com similaridade alta ---
CNPJ_A = "43.182.607/0001-42"
CNPJ_B = "54.930.781/0001-42"
CNPJ_A_OCR = "43.182.607/0001-43"  # último dígito trocado: inválido


def _sim_alta(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_BAIXO", 0.0)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.0)  # toda similaridade é "alta"
    monkeypatch.setattr(segmentacao, "perguntar_llm_mesmo_documento", lambda a, b: pytest.fail("não deveria perguntar"))


def test_similaridade_alta_com_dois_cnpjs_validos_diferentes_abre_documento(monkeypatch):
    _sim_alta(monkeypatch)
    corpo = "folha de ponto marcações entrada saída horas extras"
    docs = segmentar([_cnpj_texto(CNPJ_A, corpo), _cnpj_texto(CNPJ_B, corpo)])
    assert intervalos(docs) == [(1, 1), (2, 2)] and not docs[1].ambiguo


def test_similaridade_alta_com_mesmo_cnpj_continua(monkeypatch):
    _sim_alta(monkeypatch)
    corpo = "folha de ponto marcações entrada saída horas extras"
    assert intervalos(segmentar([_cnpj_texto(CNPJ_A, corpo), _cnpj_texto(CNPJ_A, corpo)])) == [(1, 2)]


def test_similaridade_alta_com_cnpj_invalido_por_ocr_continua(monkeypatch):
    _sim_alta(monkeypatch)
    corpo = "folha de ponto marcações entrada saída horas extras"
    assert intervalos(segmentar([_cnpj_texto(CNPJ_A, corpo), _cnpj_texto(CNPJ_A_OCR, corpo)])) == [(1, 2)]
    assert intervalos(segmentar([_cnpj_texto(CNPJ_A_OCR, corpo), _cnpj_texto(CNPJ_B, corpo)])) == [(1, 2)]


def test_pagina_k_de_n_tem_prioridade_sobre_cnpj_valido_diferente(monkeypatch):
    _sim_alta(monkeypatch)
    textos = [_cnpj_texto(CNPJ_A, "folha Página 1 de 2"), _cnpj_texto(CNPJ_B, "folha Página 2 de 2")]
    assert intervalos(segmentar(textos)) == [(1, 2)]


def test_consecutivos_do_mesmo_tipo_com_cnpjs_diferentes_separam(monkeypatch):
    _sim_alta(monkeypatch)
    corpo = "folha de ponto marcações entrada saída horas extras"
    textos = [_cnpj_texto(CNPJ_A, corpo), _cnpj_texto(CNPJ_A, corpo), _cnpj_texto(CNPJ_B, corpo)]
    assert intervalos(segmentar(textos)) == [(1, 2), (3, 3)]
