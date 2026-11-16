"""Segmentação em lote de UMA empresa (mesmo CNPJ, mesmo modelo por tipo): testes puros, sem banco nem rede.

python -m pytest tests/test_segmentacao_mesma_empresa.py
"""
import pytest

from app import segmentacao
from app.segmentacao import segmentar

CNPJ = "43.182.607/0001-42"
CNPJ_OCR = "43.182.607/0001-43"  # último dígito trocado pelo OCR: não fecha os dígitos verificadores
CPF_ANA = "529.982.247-25"
CPF_BRUNO = "111.444.777-35"
CPF_ANA_OCR = "529.982.247-26"  # dígito verificador errado
CABECALHO = f"ACME SERVIÇOS LTDA\nCNPJ {CNPJ}\nRua das Flores, 100 - Centro\n"


def intervalos(docs):
    return [(d.pagina_ini, d.pagina_fim) for d in docs]


def _jev(monkeypatch, p):
    """Fixa a probabilidade devolvida pelo Jev (None = indisponível) e devolve a lista das chamadas feitas.

    As páginas de folha destes testes são curtas e quase só cabeçalho, então ficam com similaridade alta; na folha real
    as linhas dominam e a similaridade entre páginas vizinhas fica baixa. O limiar alto sai do caminho."""
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.99)
    chamadas = []

    def falso(anterior, atual):
        chamadas.append((anterior, atual))
        return p
    monkeypatch.setattr(segmentacao, "prob_mesmo_documento", falso)
    return chamadas


def _sem_jev(monkeypatch):
    monkeypatch.setattr(segmentacao, "prob_mesmo_documento", lambda a, b: pytest.fail("não deveria perguntar ao Jev"))


def _contrato(nome: str, cpf: str) -> str:
    return (CABECALHO + "CONTRATO INDIVIDUAL DE TRABALHO\nPelo presente instrumento particular, de um lado ACME SERVIÇOS "
            f"LTDA, doravante denominada EMPREGADOR, e de outro {nome}, inscrito(a) no CPF {cpf}, doravante denominado(a) "
            "EMPREGADO, têm entre si justo e contratado o seguinte: cláusula primeira função, cláusula segunda jornada de "
            "44 horas semanais, cláusula terceira salário mensal, cláusula quarta prazo indeterminado. E, por estarem de "
            "acordo, as partes assinam o presente em duas vias.\nEMPREGADOR EMPREGADO\nTestemunha 1 Testemunha 2")


def _holerite(nome: str, cpf: str) -> str:
    via = (CABECALHO + "RECIBO DE PAGAMENTO DE SALÁRIO\nReferente a março de 2026\nNome Matrícula CPF\n"
           f"{nome} 11761 {cpf}\n001 SALÁRIO 30,00 d 3.438,34\n901 INSS 364,87\nTOTAIS 3.883,76 717,56\n"
           "LÍQUIDO A RECEBER: R$ 3.166,20\nAssinatura do funcionário\n")
    return via + via  # duas vias na mesma página: o mesmo CPF duas vezes


def _folha(linhas: list[str], total: bool) -> str:
    """Página de folha de pagamento com o cabeçalho repetido; `total` põe a linha de total geral no fim."""
    corpo = "\n".join(f"{10000 + i} {nome} Conferente 4.079,58 4.079,58 389,96 172,00 3.272,85" for i, nome in enumerate(linhas))
    fim = "\nTOTAL GERAL 36 funcionários 194.251,37 200.970,63 149.610,50" if total else ""
    return (CABECALHO + "FOLHA DE PAGAMENTO\nCompetência 06/2026 - Folha mensal\nMat. Nome Cargo Salário base Proventos "
            "INSS IRRF Líquido\n" + corpo + fim)


NOMES_A = ["Alana Pimenta", "Alice Andrade", "Brenda Aragão", "Bryan Moura", "Carlos Teixeira", "Davi Sousa"]
NOMES_B = ["Luara Rocha", "Maria Rezende", "Matheus Araújo", "Natália Gomes", "Raul Santos", "Sara Viana"]
NOMES_C = ["Emanuel Pires", "Gustavo Cunha", "Henrique Garcia", "Juliana Rios", "Laura Peixoto", "Liam Carvalho"]


# --- CPF: mesma empresa e mesmo modelo, pessoas diferentes ---
def test_cpfs_so_conta_cpf_valido_e_tolera_ocr():
    assert segmentacao.cpfs(f"CPF {CPF_ANA} e de novo {CPF_ANA}") == {"52998224725"}
    assert segmentacao.cpfs("CPF 529,982.247 - 25") == {"52998224725"}  # vírgula e espaços do OCR
    assert segmentacao.cpfs(f"CPF {CPF_ANA_OCR}") == set()  # dígito verificador errado: ignorado
    assert segmentacao.cpfs(f"CNPJ {CNPJ} sem CPF, valor 123.456.789,00") == set()
    assert segmentacao.outra_pessoa(f"CPF {CPF_ANA}", f"CPF {CPF_BRUNO}")
    assert not segmentacao.outra_pessoa(f"CPF {CPF_ANA}", f"CPF {CPF_ANA}")
    assert not segmentacao.outra_pessoa(f"CPF {CPF_ANA}", "sem identificação")
    assert not segmentacao.outra_pessoa(f"CPF {CPF_ANA}", f"CPF {CPF_ANA_OCR}")  # erro de OCR não vira outra pessoa
    assert not segmentacao.outra_pessoa(f"{CPF_ANA} {CPF_BRUNO}", f"CPF {CPF_BRUNO}")  # lista de pessoas: não decide


def test_contratos_consecutivos_da_mesma_empresa_e_funcionarios_diferentes_nao_se_fundem(monkeypatch):
    # mesmo CNPJ e mesmo texto-padrão: a similaridade é alta e antes continuava; o CPF diferente abre sem perguntar
    _sem_jev(monkeypatch)
    textos = [_contrato("Ana Liz Sales", CPF_ANA), _contrato("Bruno Souza Lima", CPF_BRUNO)]
    v = segmentacao._vetores_tfidf(textos)
    assert segmentacao._cosseno(v[0], v[1]) >= segmentacao.config.SEG_SIM_ALTO
    decisoes = []
    docs = segmentar(textos, decisoes)
    assert intervalos(docs) == [(1, 1), (2, 2)] and not docs[1].ambiguo
    assert decisoes == [(2, "abre: CPFs diferentes")]


def test_holerites_consecutivos_da_mesma_empresa_e_funcionarios_diferentes_nao_se_fundem(monkeypatch):
    _sem_jev(monkeypatch)
    textos = [_holerite("Ana Liz Sales", CPF_ANA), _holerite("Bruno Souza Lima", CPF_BRUNO), _holerite("Ana Liz Sales", CPF_ANA)]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2), (3, 3)]


def test_mesmo_cpf_ou_cpf_ilegivel_com_similaridade_alta_continua(monkeypatch):
    # continuação do mesmo documento não pode ser cortada: mesmo CPF, CPF lido errado ou página com vários CPFs
    _sem_jev(monkeypatch)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.0)  # toda similaridade é "alta"
    pagina = _contrato("Ana Liz Sales", CPF_ANA)
    assert intervalos(segmentar([pagina, pagina])) == [(1, 2)]
    assert intervalos(segmentar([pagina, _contrato("Ana Liz Sales", CPF_ANA_OCR)])) == [(1, 2)]
    lista = pagina + f"\nTestemunha CPF {CPF_BRUNO}"
    assert intervalos(segmentar([pagina, lista])) == [(1, 2)]


def test_pagina_k_de_n_tem_prioridade_sobre_cpf_diferente(monkeypatch):
    _sem_jev(monkeypatch)
    textos = [_contrato("Ana Liz Sales", CPF_ANA) + "\nPágina 1 de 2", f"Anexo: dependente CPF {CPF_BRUNO}\nPágina 2 de 2"]
    assert intervalos(segmentar(textos)) == [(1, 2)]


# --- linha de total geral: fecha a tabela ---
def test_folha_seguinte_da_mesma_empresa_abre_depois_do_total_geral(monkeypatch):
    # duas folhas de pagamento da mesma empresa, mesmo cabeçalho: a segunda abre porque a primeira já tinha fechado
    _sem_jev(monkeypatch)
    textos = [_folha(NOMES_A, total=True), _folha(NOMES_C, total=True)]
    assert segmentacao.fechado(textos[0])
    decisoes = []
    docs = segmentar(textos, decisoes)
    assert intervalos(docs) == [(1, 1), (2, 2)] and not docs[1].ambiguo
    assert decisoes == [(2, "abre: página anterior fechou a tabela (total geral)")]


def test_total_geral_abre_mesmo_com_similaridade_alta(monkeypatch):
    _sem_jev(monkeypatch)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.0)
    assert intervalos(segmentar([_folha(NOMES_A, total=True), _folha(NOMES_A, total=True)])) == [(1, 1), (2, 2)]


def test_pagina_residual_depois_do_total_geral_continua(monkeypatch):
    _sem_jev(monkeypatch)
    assinaturas = "ACME SERVIÇOS LTDA\nFolha de pagamento - Competência 06/2026\nTOTAL GERAL conferido"
    textos = [_folha(NOMES_A, total=True), assinaturas]
    assert segmentacao.residual(textos[1], textos[0])
    assert intervalos(segmentar(textos)) == [(1, 2)]


def test_fecho_vem_da_config():
    assert segmentacao.fechado("Total  Geral 10 funcionários") and segmentacao.fechado("TOTAIS GERAIS")
    assert not segmentacao.fechado("TOTAIS 3.883,76\nLÍQUIDO A RECEBER")  # totais do holerite não fecham tabela


# --- continuação esperada: a página atual traz o total geral da tabela que vinha ---
def test_ultima_pagina_da_folha_continua_quando_o_jev_fica_indeciso(monkeypatch):
    # a continuação de uma tabela repete o cabeçalho e o Jev fica no meio da faixa: antes cortava; agora continua e
    # marca o documento para a revisão. A folha seguinte abre pela linha de total, sem nova pergunta.
    chamadas = _jev(monkeypatch, 0.5)
    textos = [_folha(NOMES_A, total=False), _folha(NOMES_B, total=True), _folha(NOMES_C, total=False), _folha(NOMES_B, total=True)]
    decisoes = []
    docs = segmentar(textos, decisoes)
    assert intervalos(docs) == [(1, 2), (3, 4)]
    assert docs[0].ambiguo and docs[1].ambiguo
    assert len(chamadas) == 2
    assert [r for _, r in decisoes] == ["continua (ambíguo): continuação esperada, Jev indeciso",
                                        "abre: página anterior fechou a tabela (total geral)",
                                        "continua (ambíguo): continuação esperada, Jev indeciso"]


def test_continuacao_esperada_confirmada_pelo_jev_nao_marca_ambiguo(monkeypatch):
    _jev(monkeypatch, 0.9)
    docs = segmentar([_folha(NOMES_A, total=False), _folha(NOMES_B, total=True)])
    assert intervalos(docs) == [(1, 2)] and not docs[0].ambiguo


def test_jev_veta_a_continuacao_esperada(monkeypatch):
    # holerite seguido de uma folha de pagamento de uma página (que traz o total geral): o Jev vê outro documento
    _jev(monkeypatch, 0.05)
    docs = segmentar([_holerite("Ana Liz Sales", CPF_ANA), _folha(NOMES_A, total=True)])
    assert intervalos(docs) == [(1, 1), (2, 2)] and not docs[1].ambiguo


def test_continuacao_esperada_sem_jev_abre_e_marca_ambiguo(monkeypatch):
    # sem LLM não há quem vete: não funde por conta própria
    _jev(monkeypatch, None)
    docs = segmentar([_folha(NOMES_A, total=False), _folha(NOMES_B, total=True)])
    assert intervalos(docs) == [(1, 1), (2, 2)] and docs[1].ambiguo


def test_modo_regras_nao_chama_o_jev_na_continuacao_esperada(monkeypatch):
    monkeypatch.setattr(segmentacao.config, "CLASSIFICADOR", "regras")
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.99)
    monkeypatch.setattr(segmentacao.llm, "jev_sim_nao", lambda *a, **k: pytest.fail("rede em modo regras"))
    docs = segmentar([_folha(NOMES_A, total=False), _folha(NOMES_B, total=True)])
    assert intervalos(docs) == [(1, 1), (2, 2)] and docs[1].ambiguo


# --- continuação esperada: 'Página k de N' anunciou a página e a paginação dela não foi lida ---
RUIDO = "top eutbea S9'9STTIT ertocso VELLyvr T99ILST soprpuopuny TVYTO TVIOL voar ajuaraguoy SOJEOOISPA PURNAPA " * 3


def test_pagina_anunciada_sem_paginacao_legivel_continua(monkeypatch):
    # 'Página 1 de 2' e a página 2 veio girada (OCR ilegível, sem CNPJ nem paginação): antes abria por similaridade baixa
    chamadas = _jev(monkeypatch, 0.5)
    textos = [_folha(NOMES_A, total=False) + "\nPágina 1 de 2", RUIDO]
    decisoes = []
    docs = segmentar(textos, decisoes)
    assert intervalos(docs) == [(1, 2)] and docs[0].ambiguo and len(chamadas) == 1
    assert decisoes == [(2, "continua (ambíguo): continuação esperada, Jev indeciso")]


def test_pagina_anunciada_vale_so_para_as_paginas_que_faltam(monkeypatch):
    # o documento anunciou UMA página a mais: a terceira página, de outro assunto, abre pela similaridade baixa
    chamadas = _jev(monkeypatch, 0.5)
    outro = "ATESTADO MÉDICO atesto que o paciente esteve em consulta CID afastamento dias de repouso médico CRM " * 3
    textos = [_folha(NOMES_A, total=False) + "\nPágina 1 de 2", RUIDO, outro]
    assert intervalos(segmentar(textos)) == [(1, 2), (3, 3)]
    assert len(chamadas) == 1


def test_pagina_anunciada_nao_vence_outra_pessoa_nem_veto_do_jev(monkeypatch):
    _sem_jev(monkeypatch)
    textos = [_contrato("Ana Liz Sales", CPF_ANA) + "\nPágina 1 de 2", _contrato("Bruno Souza Lima", CPF_BRUNO)]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]
    _jev(monkeypatch, 0.1)
    textos = [_folha(NOMES_A, total=False) + "\nPágina 1 de 2", RUIDO]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]


def test_documento_paginado_completo_nao_espera_continuacao(monkeypatch):
    # 'Página 1 de 1': nada foi anunciado; a página seguinte, sem relação, abre sem perguntar
    _sem_jev(monkeypatch)
    textos = [_folha(NOMES_A, total=False) + "\nPágina 1 de 1", RUIDO]
    assert intervalos(segmentar(textos)) == [(1, 1), (2, 2)]


# --- CNPJ lido errado pelo OCR não é outra empresa ---
def test_cnpj_com_erro_de_ocr_nao_corta_a_pagina_residual(monkeypatch):
    # última página da folha só com o cabeçalho e uma linha; o OCR trocou um dígito do CNPJ. Antes abria por 'CNPJ diferente'
    _sem_jev(monkeypatch)
    monkeypatch.setattr(segmentacao.config, "SEG_SIM_ALTO", 0.99)
    rabo = f"ACME SERVIÇOS LTDA\nCNPJ {CNPJ_OCR}\nRua das Flores, 100 - Centro\nFOLHA DE PAGAMENTO\n18605"
    textos = [_folha(NOMES_A, total=False), rabo]
    assert segmentacao.cnpj(textos[0]) != segmentacao.cnpj(textos[1])
    assert intervalos(segmentar(textos)) == [(1, 2)]


def test_cnpj_com_erro_de_ocr_e_outro_assunto_ainda_abre(monkeypatch):
    # sem a regra de 'CNPJ diferente', a página de outro assunto continua abrindo pela similaridade baixa
    _sem_jev(monkeypatch)
    outro = f"CLÍNICA\nCNPJ {CNPJ_OCR}\nATESTADO MÉDICO atesto que o paciente esteve em consulta CID afastamento repouso CRM " * 2
    assert intervalos(segmentar([_folha(NOMES_A, total=False), outro])) == [(1, 1), (2, 2)]
