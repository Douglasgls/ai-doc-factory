"""Módulo de anonimização: unidade (sem banco, sem rede)."""
import pytest

from app import anonimizacao as a
from app.anonimizacao import anonimizar_texto, mascarar_cpf, mascarar_documentos

CPF = "529.982.247-25"  # válido


# ---------- CPF ----------

@pytest.mark.parametrize("entrada", [
    "CPF 529.982.247-25 fim",
    "CPF: 52998224725 fim",
    "CPF 529 . 982 . 247 - 25 fim",
    "CPF 529.982.247 - 25 fim",
    "CPF 529.982.247-2 5 fim".replace("2 5", "25"),
    "529.982.247-25 fim",
    "52998224725 fim",  # sem rótulo: vale porque o dígito verificador bate
])
def test_cpf_em_varias_formas(entrada):
    saida = anonimizar_texto(entrada)
    assert "[CPF]" in saida and "529" not in saida and "247" not in saida
    assert saida.endswith("fim")


def test_cpf_com_rotulo_tolera_digito_perdido_pelo_ocr():
    assert anonimizar_texto("CPF 529.982.247-2") == "CPF [CPF]"


def test_numero_de_11_digitos_invalido_sem_rotulo_nao_vira_cpf():
    assert anonimizar_texto("Protocolo 12345678900") == "Protocolo 12345678900"  # dígitos verificadores não batem


def test_mascarar_cpf():
    assert mascarar_cpf("123.456.789-09") == "***.456.789-**"
    assert mascarar_cpf("12345678909") == "***.456.789-**"
    assert mascarar_cpf("***.456.789-**") == "***.456.789-**"  # idempotente
    assert mascarar_cpf("lixo") == "***"
    assert mascarar_cpf(None) == "***"


def test_mascarar_documentos_mantem_o_resto_e_nao_mexe_em_nome():
    t = "Maria da Silva CPF 529.982.247-25 RG 12.345.678-9 PIS 123.45678.90-1 nasc 01/02/1990"
    s = mascarar_documentos(t)
    assert s == "Maria da Silva CPF ***.982.247-** RG *** PIS ***.*****.**-* nasc 01/02/1990"
    assert mascarar_documentos(s) == s  # idempotente
    assert mascarar_documentos(None) is None and mascarar_documentos("") == ""


# ---------- PIS, RG, nascimento ----------

def test_pis_pontuado_e_com_rotulo():
    assert anonimizar_texto("PIS 123.45678.90-1") == "PIS [PIS]"
    assert anonimizar_texto("Cadastro 123.45678.90-1") == "Cadastro [PIS]"
    assert anonimizar_texto("PIS/PASEP: 12345678901") == "PIS/PASEP: [PIS]"


@pytest.mark.parametrize("entrada,esperado", [
    ("RG 12.345.678-9", "RG [RG]"),
    ("RG: 1234567 SSP/SP", "RG: [RG] SSP/SP"),  # o órgão emissor não identifica ninguém
    ("Identidade n° 12.345.678-X", "Identidade n° [RG]"),
])
def test_rg_por_rotulo(entrada, esperado):
    assert anonimizar_texto(entrada) == esperado


def test_rg_sem_digitos_suficientes_fica():
    assert anonimizar_texto("RG 12") == "RG 12"


@pytest.mark.parametrize("entrada", [
    "Nascimento: 01/02/1990", "Data de nasc. 01/02/1990", "Data de nascimento\n01/02/1990", "Nasc 1/2/90",
])
def test_nascimento_por_rotulo(entrada):
    assert "[NASCIMENTO]" in anonimizar_texto(entrada) and "1990" not in anonimizar_texto(entrada)


def test_datas_e_horarios_comuns_ficam():
    t = "Admissão 08/07/2017 Data do exame: 11/01/2025\n01 ter 07:30 11:35 12:30 16:55 08:17\nTotal de horas: 163:08"
    assert anonimizar_texto(t) == t


def test_folha_de_ponto_continua_intacta():
    t = ("FOLHA DE PONTO\nCompetência 04/2025\n07:30 - 11:30 / 12:30 - 16:30\n"
         "01 ter 07:29 11:35 12:30 16:55 08:17\n02 qua 07:38 11:35 12:25 16:48 08:27\nHoras extras: 03:31 Faltas: 2")
    assert anonimizar_texto(t) == t


# ---------- CNPJ ----------

def test_cnpj_nao_e_mascarado():
    t = "CNPJ 03.412.689/0001-50 ou 03412689000150 ou CNP) 39.106.754/0001-66"
    assert anonimizar_texto(t) == t
    assert mascarar_documentos(t) == t


def test_cnpj_nao_e_confundido_com_cpf():
    t = "Empresa X inscrita no CNPJ 11.222.333/0001-81, CPF 529.982.247-25"
    assert anonimizar_texto(t) == "Empresa X inscrita no CNPJ 11.222.333/0001-81, CPF [CPF]"


# ---------- nomes ----------

def test_nome_por_rotulo():
    assert anonimizar_texto("Nome: Maria da Silva Santos") == "Nome: [NOME]"
    assert anonimizar_texto("Funcionário: Carlos Eduardo Souza Matrícula 123") == "Funcionário: [NOME] Matrícula 123"
    assert anonimizar_texto("Colaborador Ana") == "Colaborador [NOME]"
    assert anonimizar_texto("Paciente: José Pereira") == "Paciente: [NOME]"


def test_nome_depois_do_rotulo_nao_engole_o_proximo_rotulo():
    assert anonimizar_texto("Nome: Maria Souza Cargo: Vendedor") == "Nome: [NOME] Cargo: Vendedor"
    assert anonimizar_texto("Nome Cargo Salário") == "Nome Cargo Salário"


def test_nome_em_linha_solta_exemplo_do_lote_L0001():
    t = "Cargo\nAuxiliar Administrativo\nAntony da Mata Pereira\nHorário contratual Setor"
    assert anonimizar_texto(t) == "Cargo\nAuxiliar Administrativo\n[NOME]\nHorário contratual Setor"


def test_nome_no_meio_da_frase_e_ao_lado_do_cpf():
    t = "que o(a) Sr(a). Luiz Henrique Gonçalves, portador(a) do CPF 529.982.247-25, foi atendido"
    assert anonimizar_texto(t) == "que o(a) Sr(a). [NOME], portador(a) do CPF [CPF], foi atendido"
    assert anonimizar_texto("Liam Brito 529.982.247-25 |") == "[NOME] [CPF] |"


def test_nome_na_linha_da_tabela_separa_do_cargo():
    t = "45637 Ana Liz Pastor Azevedo Técnico de Segurança do Trabalho 4.862,48"
    assert anonimizar_texto(t) == "45637 [NOME] Técnico de Segurança do Trabalho 4.862,48"
    t = "52524 Benício Rocha Atendente 3.834,35"
    assert anonimizar_texto(t) == "52524 [NOME] Atendente 3.834,35"


def test_nome_quebrado_em_duas_linhas():
    t = "e de outro Ana Carolina Cardoso\nAzevedo, inscrito(a) no CPF 529.982.247-25"
    assert anonimizar_texto(t) == "e de outro [NOME]\n[NOME], inscrito(a) no CPF [CPF]"


def test_medico_com_crm():
    assert anonimizar_texto("Dr(a). Cecília Mendonça Montenegro - CRM-SE 125173") == "Dr(a). [NOME] - CRM-SE 125173"


@pytest.mark.parametrize("termo", [
    "Recursos Humanos", "Auxiliar Administrativo", "Folha de Pagamento", "Atestado Médico", "Contrato de Trabalho",
    "Recibo de Férias", "Folha de Ponto", "Atestado de Saúde Ocupacional", "Técnico de Segurança do Trabalho",
    "RECIBO DE PAGAMENTO DE SALÁRIO", "FOLHA DE PAGAMENTO", "ATESTADO MÉDICO", "CONTRATO INDIVIDUAL DE TRABALHO",
    "Analista de RH", "Operador de Máquinas", "Supervisor de Logística", "DOCUMENTO SINTÉTICO PARA",
    "ADICIONAL NOTURNO", "COPARTICIPAÇÃO PLANO DE SAÚDE", "Assinatura do funcionário", "Horário contratual",
])
def test_termos_de_documento_nao_sao_apagados(termo):
    assert anonimizar_texto(termo) == termo
    assert anonimizar_texto(f"x\n{termo}\ny") == f"x\n{termo}\ny"


def test_todos_os_termos_documentais_da_lista_sobrevivem():
    for termo in a.TERMOS_DOCUMENTAIS:
        assert termo in anonimizar_texto(f"linha\n{termo}\nlinha")


def test_nome_da_empresa_pela_linha_do_cnpj_fica():
    t = ("DA CONCEIÇÃO Silva\nCNPJ 03.412.689/0001-50\n\n"
         "Recebi da empresa DA CONCEIÇÃO Silva, inscrita no CNPJ 03.412.689/0001-50, a importância\n"
         "Pereira Alves Souza\n")
    s = anonimizar_texto(t)
    assert s.startswith("DA CONCEIÇÃO Silva\nCNPJ") and "empresa DA CONCEIÇÃO Silva, inscrita" in s
    assert s.endswith("[NOME]\n")


def test_empresa_com_sufixo_ltda_fica():
    assert anonimizar_texto("de um lado Farias Costela LTDA, inscrita") == "de um lado Farias Costela LTDA, inscrita"


def test_endereco_e_cidade_ficam():
    t = "Pátio de Castro, 41 - Marques Alegre/MA\nTrevo Sousa, 45"
    assert anonimizar_texto(t) == t


def test_vazio_e_none():
    assert anonimizar_texto("") == "" and anonimizar_texto(None) is None


def test_idempotente():
    t = "Nome: Maria Souza CPF 529.982.247-25 Nascimento 01/02/1990"
    uma = anonimizar_texto(t)
    assert anonimizar_texto(uma) == uma


# ---------- estruturas ----------

def test_mascarar_estrutura_e_campos():
    campos = {"nome": "Maria Silva", "cpf": "52998224725", "rg": "123456789", "matricula": "77"}
    assert a.mascarar_campos(campos) == {"nome": "Maria Silva", "cpf": "***.982.247-**", "rg": "***", "matricula": "77"}
    r = a.mascarar_estrutura({"cpf": "52998224725", "valores": [{"valor": "x 529.982.247-25"}], "n": 3})
    assert r == {"cpf": "***.982.247-**", "valores": [{"valor": "x ***.982.247-**"}], "n": 3}
    assert a.anonimizar_estrutura({"a": ["CPF 529.982.247-25"]}) == {"a": ["CPF [CPF]"]}
    assert a.e_mascarado("***.982.247-**") and not a.e_mascarado("52998224725")
