"""Anonimização determinística de dados pessoais (sem LLM, sem modelos): regex e heurísticas de linha.

- anonimizar_texto: CPF, RG, PIS, data de nascimento e nomes viram marcadores. Usado antes de enviar texto a LLM.
- mascarar_documentos: só identificadores (CPF, RG, PIS), mantendo o resto. Usado nas respostas da API.
- mascarar_cpf: '123.456.789-09' -> '***.456.789-**'.

Fica de fora de propósito: CNPJ (é da empresa e é a chave de agrupamento do Goal 7), datas e horários comuns
(as marcações da folha de ponto precisam continuar intactas) e termos de tipo documental, que o classificador lê.

Limitações: o nome sem rótulo é achado por heurística (linha com 2 a 6 palavras capitalizadas), então erra
nos dois sentidos, principalmente com OCR ruim. Não é garantia de anonimização nem conformidade LGPD por si só.
"""
import re
import unicodedata

M_CPF, M_RG, M_PIS, M_NOME, M_NASC = "[CPF]", "[RG]", "[PIS]", "[NOME]", "[NASCIMENTO]"

# ---------------------------------------------------------------------------------------------
# Constantes de nome: conectivos, rótulos e lista de exclusão (termos de documento e de RH)
# ---------------------------------------------------------------------------------------------
CONECTIVOS = frozenset({"da", "de", "do", "dos", "das", "e"})
NOME_PALAVRAS_MAX = 6  # total de palavras do nome, contando conectivos

# Palavras que NUNCA fazem parte de um nome: rótulos de campos, títulos e termos de documento, cargos e setores.
# Comparadas sem acento e sem caixa. Servem de fronteira: "Ana Liz Azevedo Técnico de Segurança" vira nome + cargo.
EXCLUSAO_PALAVRAS = frozenset("""
    recursos humanos folha pagamento pagamentos ponto atestado medico medica saude ocupacional contrato trabalho
    recibo ferias aso holerite salario salarios contracheque demonstrativo comprovante declaracao termo aviso
    cargo funcao setor departamento secao matricula mat admissao demissao competencia referencia periodo
    horario horarios contratual jornada entrada saida retorno intervalo horas extras faltas total totais geral
    nome nomes cpf rg pis pasep nit cnpj cnp crm cid data cidade endereco telefone assinatura assinaturas
    funcionario funcionaria colaborador colaboradora empregado empregada empregador empregadora trabalhador
    trabalhadora paciente medico medica coordenador coordenadora examinador examinadora responsavel testemunha
    contratante contratada contratado outorgante pcmso exame exames parecer apto inapto restricao risco riscos
    agente fator tipo admissional periodico mudanca demissional resultado normal alterado clinico complementares
    discriminacao proventos descontos desconto liquido receber valor salario bruto base inss irrf fgts vale
    transporte alimentacao referencia codigo cod descricao vias pagina paginas de
    ocorrencias ocorrencia folga dsr falta rubrica observacao observacoes documento documentos sintetico
    sintetica dados ficticios ficticio protocolado recebido recebida copia original imagem escaneado
    auxiliar assistente analista operador tecnico tecnica supervisor supervisora gerente coordenacao diretor
    diretora motorista vendedor vendedora recepcionista almoxarife eletricista soldador atendente conferente
    administrativo administrativa financeiro financeira contabil producao logistica manutencao comercial
    almoxarifado atendimento seguranca limpeza maquinas estagiario estagiaria encarregado encarregada
    clausula parte partes presente instrumento particular lado outro sede objeto prazo experiencia
    ltda eireli epp sa eni empresa companhia comercio servicos industria clinica hospital laboratorio
    janeiro fevereiro abril maio junho julho agosto setembro outubro novembro dezembro
    segunda terca quarta quinta sexta sabado domingo seg ter qua qui sex sab dom
    brasil federal estado municipal social previdencia ministerio republica
    adicional noturno periculosidade insalubridade comissao gratificacao decimo terceiro coparticipacao plano
    odontologico convenio pensao alimenticia sindical contribuicao base fisico quimico biologico ergonomico
    acidente levantamento transporte manual peso postura ruido calor poeiras minerais solventes vapores
    organicos eletricidade altura agentes audiometria hemograma eletrocardiograma espirometria glicemia
    acuidade visual psicossocial avaliacao aptidao
    emprega dor para por com sem em no na nos nas ao aos um uma ou como mais pela pelo pelas pelos sob sobre entre ate
    rua avenida av travessa alameda rodovia estrada praca quadra vila chacara distrito nucleo patio morro
    estacao largo loteamento conjunto bairro residencial lote
""".split())

# Frases de documento/RH que o classificador precisa ler. A fronteira por palavra já as protege; a lista de
# frases existe para o avaliador e para quem quiser conferir o que deve sobreviver à anonimização.
TERMOS_DOCUMENTAIS = (
    "Recursos Humanos", "Auxiliar Administrativo", "Folha de Pagamento", "Folha de Ponto", "Atestado Médico",
    "Atestado de Saúde Ocupacional", "Contrato de Trabalho", "Recibo de Férias", "Recibo de Pagamento de Salário",
    "Técnico de Segurança do Trabalho", "Analista de RH", "ASO", "Holerite", "Dados do Trabalhador",
)

# Rótulos que introduzem um nome na mesma linha. Maiúscula inicial obrigatória no rótulo (evita "funcionário"
# no meio de uma frase) e valor na mesma linha.
_ROTULOS_NOME = (r"Nome(?:\s+completo)?", r"Funcionári[oa]", r"Colaborador(?:a)?", r"Paciente", r"Empregad[oa]",
                 r"Trabalhador(?:a)?", r"Benefici[aá]ri[oa]", r"Sr\(a\)\.?", r"Sra?\.", r"Titular", r"Nome do (?:funcion[aá]rio|paciente)")

# Sequência seguida de número ("Fulano, 442") ou de /UF ("Cidade/MA", "- Cidade/MA") é endereço, cidade ou data de
# local, não pessoa.
_DEPOIS_ENDERECO = re.compile(r"^[ \t]*(?:,[ \t]*\d|/[ \t]?[A-Z]{2}\b)")

# ---------------------------------------------------------------------------------------------
# Identificadores
# ---------------------------------------------------------------------------------------------
_NAO_DIGITO = r"(?<![\d.,/\-])"  # não começa no meio de outro número (nem de CNPJ com barra)
_CPF_PONTUADO = re.compile(_NAO_DIGITO + r"\d{3}[ \t]?[.,][ \t]?\d{3}[ \t]?[.,][ \t]?\d{3}[ \t]?[-–—][ \t]?\d{2}(?!\d)")
_CPF_PLANO = re.compile(_NAO_DIGITO + r"\d{11}(?![\d]|[.,/\-]\d)")
_CPF_ROTULO = re.compile(r"(\bCPF\b[ \t]*(?:n[ºo°]\.?)?[ \t]*[:.\-]?[ \t]*)(\d[\d.,\-–— \t]{7,16}\d)", re.I)
_PIS_PONTUADO = re.compile(_NAO_DIGITO + r"\d{3}[ \t]?\.[ \t]?\d{5}[ \t]?\.[ \t]?\d{2}[ \t]?-[ \t]?\d(?!\d)")
_PIS_ROTULO = re.compile(r"(\b(?:PIS|PASEP|NIT)(?:[ \t/]+(?:PASEP|NIT))?\b[ \t]*(?:n[ºo°]\.?)?[ \t]*[:.\-]?[ \t]*)(\d[\d.\-– \t]{7,16}\d)", re.I)
_RG_ROTULO = re.compile(
    r"(\b(?:R\.?[ \t]?G\.?|Identidade|Registro[ \t]+Geral)\b[ \t]*(?:n[ºo°]\.?)?[ \t]*[:.\-]?[ \t]*)"
    r"(\d[\d.\- \t]{3,14}[\dXx](?:[ \t]*[-/][ \t]*[A-Z]{2,5})?)", re.I)
_NASC_ROTULO = re.compile(
    r"(\b(?:Data[ \t]+de[ \t]+nasc(?:imento|\.)?|Data[ \t]+nasc(?:imento|\.)?|Nascimento|Nasc\.?)\b[ \t]*[:.\-]?[\s]{0,3})"
    r"(\d{1,2}[ \t]?[/.\-][ \t]?\d{1,2}[ \t]?[/.\-][ \t]?\d{2,4})", re.I)
_CNPJ_LINHA = re.compile(r"\d{2}\.?\d{3}\.?\d{3}/\d{4}-?\d{2}|\bCNP\S{0,2}\b|\bCNPJ\b", re.I)


def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _cpf_valido(d: str) -> bool:
    if len(d) != 11 or len(set(d)) == 1:
        return False
    for n in (9, 10):
        soma = sum(int(x) * (n + 1 - i) for i, x in enumerate(d[:n]))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def mascarar_cpf(valor) -> str:
    """'123.456.789-09' ou '12345678909' -> '***.456.789-**'. Já mascarado volta como está; fora do padrão vira '***'."""
    s = str(valor if valor is not None else "")
    if "*" in s:
        return s
    d = _digitos(s)
    if len(d) != 11:
        return "***"
    return f"***.{d[3:6]}.{d[6:9]}-**"


def _mascara_pis(m: re.Match) -> str:
    return "***.*****.**-*"


def _subst_ident(texto: str, cpf, rg, pis, rg_pis_rotulo=True) -> str:
    """Aplica as máscaras de identificador. cpf/rg/pis são funções (re.Match -> str)."""
    texto = _CPF_ROTULO.sub(lambda m: m.group(1) + cpf(m.group(2)), texto)
    texto = _CPF_PONTUADO.sub(lambda m: cpf(m.group(0)), texto)
    texto = _CPF_PLANO.sub(lambda m: cpf(m.group(0)) if _cpf_valido(m.group(0)) else m.group(0), texto)
    texto = _PIS_ROTULO.sub(lambda m: m.group(1) + pis(m.group(2)), texto)
    texto = _PIS_PONTUADO.sub(lambda m: pis(m.group(0)), texto)
    texto = _RG_ROTULO.sub(lambda m: m.group(1) + rg(m.group(2)) if len(_digitos(m.group(2))) >= 5 else m.group(0), texto)
    return texto


def mascarar_documentos(texto: str | None) -> str | None:
    """Máscara só de CPF, RG e PIS (para respostas da API). Nomes e datas ficam."""
    if not texto:
        return texto
    return _subst_ident(texto, mascarar_cpf, lambda v: "***", _mascara_pis)


# ---------------------------------------------------------------------------------------------
# Nomes
# ---------------------------------------------------------------------------------------------
_PALAVRA = re.compile(r"[^\W\d_][\w'’]*", re.UNICODE)


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()


def _empresas_pela_linha_do_cnpj(linhas: list[str]) -> set[str]:
    """Linha logo antes (ou a própria) da linha do CNPJ é o nome da empresa: nunca vira [NOME]."""
    nomes = set()
    for i, ln in enumerate(linhas):
        if _CNPJ_LINHA.search(ln):
            for j in (i - 1, i - 2):
                if j >= 0 and linhas[j].strip():
                    nomes.add(_norm(linhas[j]).strip())
                    break
    for m in re.finditer(r"empresa[ \t]+([^,\n]{2,60}?)[ \t]*,[ \t]*inscrit", "\n".join(linhas)):
        nomes.add(_norm(m.group(1)).strip())
    for m in re.finditer(r"lado[ \t]+([^,\n]{2,60}?)[ \t]*,[ \t]*inscrit", "\n".join(linhas)):
        nomes.add(_norm(m.group(1)).strip())
    return {n for n in nomes if n}


def _classe(palavra: str) -> str:
    """'cap' (pode compor nome), 'con' (conectivo) ou 'x' (quebra a sequência)."""
    n = _norm(palavra)
    if n in EXCLUSAO_PALAVRAS:
        return "x"
    if palavra.lower() in CONECTIVOS and palavra.islower():
        return "con"
    if palavra[0].isupper() and len(palavra) >= 2 and not (palavra.isupper() and len(palavra) <= 2):
        return "cap"
    return "x"


def _sequencias_de_nome(linha: str, minimo_cap: int = 2) -> list[tuple[int, int]]:
    """Spans (ini, fim) de sequências de 2 a 6 palavras capitalizadas, com conectivos só no meio."""
    palavras = list(_PALAVRA.finditer(linha))
    spans, atual = [], []

    def fechar():
        while atual and atual[-1][1] == "con":
            atual.pop()
        caps = sum(1 for _, c in atual if c == "cap")
        if caps >= minimo_cap and len(atual) <= NOME_PALAVRAS_MAX:
            spans.append((atual[0][0].start(), atual[-1][0].end()))
        atual.clear()

    anterior_fim = None
    for m in palavras:
        c = _classe(m.group(0))
        colada = anterior_fim is not None and re.fullmatch(r"[ \t]+", linha[anterior_fim:m.start()] or "") is not None
        if atual and not colada:
            fechar()
        if c == "x" or (c == "con" and not atual):
            fechar()
        else:
            atual.append((m, c))
        anterior_fim = m.end()
    fechar()
    return spans


def _nome_por_rotulo(linha: str) -> str:
    padrao = re.compile(r"(\b(?:" + "|".join(_ROTULOS_NOME) + r")[ \t]*[:\-]?[ \t]*)(?=[A-ZÀ-Ý])")
    saida, pos = [], 0
    for m in padrao.finditer(linha):
        if m.start() < pos:
            continue
        resto = linha[m.end():]
        spans = _sequencias_de_nome(resto, minimo_cap=1)
        if spans and spans[0][0] == 0:
            fim = m.end() + spans[0][1]
            saida.append(linha[pos:m.end()] + M_NOME)
            pos = fim
    return "".join(saida) + linha[pos:]


_SUFIXO_EMPRESA = re.compile(r"^[ \t]+(?:LTDA|Ltda|EIRELI|Eireli|EPP|MEI|EI|ME|S/?A|S\.A\.?)\b")
_PALAVRA_SOLTA = re.compile(r"^([ \t]*)([^\W\d_][\w'’]*)(?=[ \t]*(?:[,;.]|$))")


def _e_empresa(trecho: str, depois: str, empresas: set[str]) -> bool:
    n = _norm(trecho).strip()
    return bool(_SUFIXO_EMPRESA.match(depois)) or any(
        n == e or re.search(rf"\b{re.escape(n)}\b", e) for e in empresas)


def _anonimizar_nomes(texto: str) -> str:
    linhas = texto.split("\n")
    empresas = _empresas_pela_linha_do_cnpj(linhas)
    saida = []
    continua = False  # a linha anterior terminou num nome: a próxima pode começar com o resto do sobrenome
    for ln in linhas:
        if _norm(ln).strip() in empresas:
            saida.append(ln)  # cabeçalho da empresa: fica
            continua = False
            continue
        if continua:
            m = _PALAVRA_SOLTA.match(ln)
            if m and _classe(m.group(2)) == "cap":
                ln = m.group(1) + M_NOME + ln[m.end():]
        ln = _nome_por_rotulo(ln)
        continua = False
        for ini, fim in reversed(_sequencias_de_nome(ln)):
            if _e_empresa(ln[ini:fim], ln[fim:], empresas) or _DEPOIS_ENDERECO.match(ln[fim:]):
                continue
            if not ln[fim:].strip() and len(_PALAVRA.findall(ln[ini:fim])) < NOME_PALAVRAS_MAX:
                continua = True  # nome no fim da linha (OCR quebrou a linha no meio do nome)
            ln = ln[:ini] + M_NOME + ln[fim:]
        saida.append(ln)
    return "\n".join(saida)


# ---------------------------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------------------------
def anonimizar_texto(texto: str | None) -> str | None:
    """Troca CPF, RG, PIS, nascimento e nomes por marcadores. Determinístico."""
    if not texto:
        return texto
    t = _NASC_ROTULO.sub(lambda m: m.group(1) + M_NASC, texto)
    t = _subst_ident(t, lambda v: M_CPF, lambda v: M_RG, lambda v: M_PIS)
    return _anonimizar_nomes(t)


def anonimizar_estrutura(valor):
    """Anonimiza todas as strings de um dict/list (para state de LLM que mistura texto livre)."""
    if isinstance(valor, str):
        return anonimizar_texto(valor)
    if isinstance(valor, dict):
        return {k: anonimizar_estrutura(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [anonimizar_estrutura(v) for v in valor]
    return valor


CAMPOS_IDENTIFICADORES = ("cpf", "rg", "pis")


def mascarar_campo(nome: str, valor):
    """Valor de um campo extraído, para a resposta da API: cpf/rg/pis mascarados; o resto passa por
    mascarar_documentos (um valor livre pode conter um CPF)."""
    if not isinstance(valor, str):
        return valor
    if nome == "cpf":
        return mascarar_cpf(valor)
    if nome in ("rg", "pis"):
        return valor if "*" in valor else "***"
    return mascarar_documentos(valor)


def mascarar_campos(campos: dict | None) -> dict | None:
    return None if campos is None else {k: mascarar_campo(k, v) for k, v in campos.items()}


def mascarar_estrutura(valor):
    """Percorre dict/list: chaves cpf/rg/pis são mascaradas; toda string passa por mascarar_documentos."""
    if isinstance(valor, dict):
        return {k: (mascarar_campo(k, v) if k in CAMPOS_IDENTIFICADORES and isinstance(v, str) else mascarar_estrutura(v))
                for k, v in valor.items()}
    if isinstance(valor, list):
        return [mascarar_estrutura(v) for v in valor]
    if isinstance(valor, str):
        return mascarar_documentos(valor)
    return valor


def e_mascarado(valor) -> bool:
    return isinstance(valor, str) and "*" in valor
