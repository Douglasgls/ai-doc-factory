"""Score de conformidade da empresa prestadora (Goal 7): funções puras, sem banco e sem LLM.

A empresa é identificada pelo CNPJ da prestadora (validado em código); seus documentos são reunidos entre
lotes. O contrato do lote é fonte cadastrada, não palpite: em lote com contrato, o documento sem CNPJ válido
(ou sem distinção prestadora/tomadora) liga ao prestador do contrato (origem "contrato"), e um CNPJ extraído
válido e diferente do contrato também liga ao prestador do contrato, com a divergência `cnpj_diferente_do_contrato`
(conta na Consistência). Lote sem contrato exige CNPJ extraído válido com distinção prestadora/tomadora. Há três níveis, com a mesma fórmula e os mesmos pesos: geral da empresa, por tipo e por documento.

Convenções (documentadas aqui para o teste ser determinístico):
- Nota de um critério = bons / (bons + ruins). Itens pendentes ficam fora da conta (nunca valem zero).
- Critério "não se aplica" (ex.: Completude por documento, Validade de holerite, contrato por prazo
  indeterminado) ou pendente (aplicável, mas sem nada analisável) sai da conta e seu peso é redistribuído:
  peso efetivo = peso / soma dos pesos dos critérios calculados. Sem critério calculado, não há score.
- score_bruto = soma(peso efetivo x nota). O score inteiro arredonda o bruto ao inteiro mais próximo
  (0,5 sobe) ANTES de classificar: 84,5 vira 85 (Regular); 84,49 vira 84 (Atenção).
- Cada item ruim desconta peso_efetivo / (bons + ruins) pontos, com 4 casas; então
  score_bruto + soma(descontos) = 100 com tolerância de 0,0005 por desconto. O score inteiro não fecha.
- Vencer na data de referência ainda conta como válido (vence ao fim do dia).
- `provisorio` só com documento não analisado, obrigatório pendente ou critério aplicável inteiro pendente.
  Campo ausente aparece nas pendências, mas não torna o score provisório.
- No nível por tipo, documento em revisão só conta como pendente se puder ser desse tipo (tipo sugerido igual
  ou desconhecido); a pendência torna o score do tipo provisório, sem mudar a nota. O nível por documento não tem pendentes.
- Consistência: razão social é comparada entre os documentos da empresa (o CNPJ é a chave que os reúne);
  nome, matrícula e data de admissão só dentro do mesmo CPF válido. Valor ausente não é divergência.
  Exceção: em lote com contrato, o CNPJ extraído válido vs o CNPJ do contrato conta UM campo por empresa
  (como a razão social): coerente se todos batem; divergente (`cnpj_diferente_do_contrato`) se algum difere, e aí o
  desconto vale só para os documentos divergentes. Documento ligado pelo contrato sem CNPJ válido não entra.
  Um CNPJ igual ao do contrato, mas sem `distingue_prestadora`, também liga pelo contrato (origem "contrato").
"""
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime

from app import config

# ---------------------------------------------------------------------------------------------
# Configuração (bloco único)
# ---------------------------------------------------------------------------------------------
PESOS = {"completude": 40, "validade": 35, "consistencia": 25}
FAIXAS = (("Regular", 85), ("Atenção", 65), ("Crítico", 0))  # (nome, score inteiro mínimo, inclusivo)
OBRIGATORIOS = ("aso", "contrato_trabalho", "holerite", "folha_pagamento", "folha_ponto")
ESTADOS_ANALISADOS = ("classificado", "revisado")

# Validade por tipo. Com prazo_meses: vence esse tanto de meses depois do campo; sem: o campo é o vencimento.
# ATENÇÃO: o prazo do ASO (12 meses) é valor de partida e PRECISA ser conferido na NR-7.
# nao_aplica: se o campo tem este valor, a validade não se aplica (contrato por prazo indeterminado).
VALIDADE = {
    "aso": {"campo": "data_exame", "prazo_meses": 12},
    "contrato_trabalho": {"campo": "data_termino", "nao_aplica": ("tipo_prazo", "indeterminado")},
}

_TODOS = tuple(config.TIPOS)
_PESSOA = ("aso", "holerite", "folha_ponto", "recibo_ferias", "atestado_medico", "contrato_trabalho")
CONSISTENCIA_EMPRESA = {"razao_social_prestadora": _TODOS}  # comparado entre os documentos da empresa
CONSISTENCIA_PESSOA = {  # comparado só entre documentos do mesmo CPF
    "nome": _PESSOA,
    "matricula": ("holerite", "folha_ponto", "recibo_ferias", "contrato_trabalho"),
    "data_admissao": ("holerite", "contrato_trabalho"),
}
CPF_ESPERADO = _PESSOA  # tipos em que o CPF é esperado (sem ele o documento não entra na comparação)

TOLERANCIA_ARREDONDAMENTO = 0.0005  # por desconto

_usados = (set(OBRIGATORIOS) | set(VALIDADE) | set(CPF_ESPERADO)
           | {t for ts in (*CONSISTENCIA_EMPRESA.values(), *CONSISTENCIA_PESSOA.values()) for t in ts})
if not _usados <= set(config.TIPOS):
    raise ValueError(f"tipos fora de config.TIPOS: {sorted(_usados - set(config.TIPOS))}")


# ---------------------------------------------------------------------------------------------
# Validação e normalização
# ---------------------------------------------------------------------------------------------
def _digitos(v) -> str:
    return re.sub(r"\D", "", str(v or ""))


def _dv(digs: str, pesos: list[int]) -> int:
    r = sum(int(d) * p for d, p in zip(digs, pesos)) % 11
    return 0 if r < 2 else 11 - r


def validar_cnpj(v) -> str | None:
    """CNPJ só com dígitos se os dígitos verificadores batem; senão None."""
    c = _digitos(v)
    if len(c) != 14 or len(set(c)) == 1:
        return None
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    if c[12] != str(_dv(c[:12], p1)) or c[13] != str(_dv(c[:13], [6, *p1])):
        return None
    return c


def validar_cpf(v) -> str | None:
    c = _digitos(v)
    if len(c) != 11 or len(set(c)) == 1:
        return None
    if c[9] != str(_dv(c[:9], list(range(10, 1, -1)))) or c[10] != str(_dv(c[:10], list(range(11, 1, -1)))):
        return None
    return c


def parse_data(valor) -> date | None:
    """Aceita date, 'AAAA-MM-DD' e 'DD/MM/AAAA'. Devolve None se ilegível."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(str(valor or "").strip(), fmt).date()
        except ValueError:
            pass
    return None


def normalizar(campo: str, valor) -> str:
    """Forma canônica para comparar: sem acento, caixa baixa, espaços e pontuação removidos."""
    s = "".join(c for c in unicodedata.normalize("NFKD", str(valor)) if not unicodedata.combining(c)).lower().strip()
    if campo == "data_admissao" and parse_data(valor):
        return parse_data(valor).isoformat()
    if campo == "matricula":
        return re.sub(r"[^a-z0-9]", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _somar_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    ano, mes = d.year + m // 12, m % 12 + 1
    bissexto = ano % 4 == 0 and (ano % 100 != 0 or ano % 400 == 0)
    dias = [31, 29 if bissexto else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mes - 1]
    return date(ano, mes, min(d.day, dias))


def score_inteiro(bruto: float) -> int:
    """Arredonda para o inteiro mais próximo, 0,5 sobe. A faixa é decidida sobre este valor."""
    return math.floor(round(bruto, 6) + 0.5)


def classificar_score(score: int) -> str:
    return next(nome for nome, minimo in FAIXAS if score >= minimo)


def analisado(d: dict) -> bool:
    return d.get("estado") in ESTADOS_ANALISADOS and d.get("tipo") in config.TIPOS


def _vazio(v) -> bool:
    return v is None or not str(v).strip()


# ---------------------------------------------------------------------------------------------
# Identificação da empresa
# ---------------------------------------------------------------------------------------------
def identificar_empresa(campos_doc: dict) -> tuple[str | None, str | None]:
    """(cnpj, None) ou (None, motivo). Nunca liga a empresa por palpite."""
    if _vazio(campos_doc.get("cnpj_prestadora")):
        return None, "CNPJ da prestadora ausente"
    cnpj = validar_cnpj(campos_doc["cnpj_prestadora"])
    if cnpj is None:
        return None, "CNPJ da prestadora inválido"
    if str(campos_doc.get("distingue_prestadora", "")).lower() != "true":
        return None, "documento não distingue prestadora e tomadora"
    return cnpj, None


def resolver_empresa(campos_doc: dict, cnpj_contrato: str | None = None) -> dict:
    """Com contrato (cnpj_contrato válido): sempre liga ao prestador do contrato. Sem contrato: identificar_empresa.
    Devolve {cnpj, motivo, origem ("extraido"|"contrato"|None), divergencia (None | {extraido, contrato})}."""
    contrato = validar_cnpj(cnpj_contrato)
    cnpj, motivo = identificar_empresa(campos_doc)
    if contrato is None:
        return {"cnpj": cnpj, "motivo": motivo, "origem": "extraido" if cnpj else None, "divergencia": None}
    if cnpj == contrato:
        return {"cnpj": contrato, "motivo": None, "origem": "extraido", "divergencia": None}
    diverge = None
    if cnpj:  # extraído válido, distingue a prestadora e é outro CNPJ
        diverge = {"extraido": cnpj, "contrato": contrato}
    return {"cnpj": contrato, "motivo": None, "origem": "contrato", "divergencia": diverge}


def agrupar_empresas(documentos: list[dict], campos: dict) -> tuple[dict, list[dict]]:
    """documentos: [{id, lote_id, tipo, estado, cnpj_contrato?}]. Devolve ({cnpj: [docs]}, [docs sem empresa]).
    Documentos analisados e em_revisao (extraídos, mas sem tipo confirmado) entram na empresa pelo CNPJ (ou pelo
    contrato do lote, ver resolver_empresa); segmentado e erro nunca têm empresa. Cada documento ligado ganha
    `origem_empresa` e, se for o caso, `divergencia_cnpj`. Documento sem empresa não afeta a nota de nenhuma empresa."""
    empresas: dict[str, list[dict]] = {}
    sem: list[dict] = []
    for d in documentos:
        if not analisado(d) and d.get("estado") != "em_revisao":
            sem.append({**d, "motivo": f"documento não analisado (estado '{d.get('estado')}', tipo '{d.get('tipo')}')"})
            continue
        r = resolver_empresa(campos.get(d["id"], {}), d.get("cnpj_contrato"))
        if r["cnpj"]:
            empresas.setdefault(r["cnpj"], []).append(
                {**d, "origem_empresa": r["origem"], "divergencia_cnpj": r["divergencia"]})
        else:
            sem.append({**d, "motivo": r["motivo"]})
    return empresas, sem


# ---------------------------------------------------------------------------------------------
# Consistência: grupos comparados (calculados uma vez por empresa) e campos faltantes
# ---------------------------------------------------------------------------------------------
def _grupos_consistencia(docs: list[dict], campos: dict):
    grupos, faltas = [], []

    def comparar(campo, tipos, membros, chave):
        valores = []
        for d in membros:
            if d["tipo"] not in tipos:
                continue
            v = campos.get(d["id"], {}).get(campo)
            if _vazio(v):
                faltas.append((d, campo, f"campo '{campo}' ausente"))
            else:
                valores.append((d, v))
        if len(valores) >= 2:
            grupos.append({"campo": campo, "chave": chave, "docs": {d["id"] for d, _ in valores},
                           "divergente": len({normalizar(campo, v) for _, v in valores}) > 1,
                           "valores": [{"documento": d["id"], "tipo": d["tipo"], "valor": v} for d, v in valores]})

    for campo, tipos in CONSISTENCIA_EMPRESA.items():
        comparar(campo, tipos, docs, None)
    # CNPJ extraído x CNPJ do contrato: UM campo comparado por empresa (como a razão social), só com documento
    # de lote com contrato e CNPJ extraído válido. Divergente: o grupo cobre só os documentos divergentes.
    comparados = [d for d in docs if d.get("divergencia_cnpj") or (d.get("origem_empresa") == "extraido"
                                                                   and validar_cnpj(d.get("cnpj_contrato")))]
    if comparados:
        div = [d for d in comparados if d.get("divergencia_cnpj")]
        g = {"campo": "cnpj_prestadora", "chave": None, "divergente": bool(div),
             "docs": {d["id"] for d in (div or comparados)}}
        if div:
            g.update(regra="cnpj_diferente_do_contrato",
                     detalhe=f"{len(div)} documento(s) com CNPJ extraído diferente do CNPJ do contrato",
                     valores=[{"documento": d["id"], "tipo": d["tipo"], "valor": d["divergencia_cnpj"]["extraido"],
                               "cnpj_contrato": d["divergencia_cnpj"]["contrato"]} for d in div])
            if len(div) == 1:
                g.update(documento=div[0]["id"], tipo=div[0]["tipo"],
                         cnpj_extraido=div[0]["divergencia_cnpj"]["extraido"],
                         cnpj_contrato=div[0]["divergencia_cnpj"]["contrato"])
        grupos.append(g)
    por_cpf: dict[str, list[dict]] = {}
    for d in docs:
        if d["tipo"] not in CPF_ESPERADO:
            continue
        bruto = campos.get(d["id"], {}).get("cpf")
        cpf = validar_cpf(bruto)
        if cpf:
            por_cpf.setdefault(cpf, []).append(d)
        else:
            faltas.append((d, "cpf", "campo 'cpf' ausente" if _vazio(bruto) else "campo 'cpf' inválido"))
    for cpf, membros in por_cpf.items():
        for campo, tipos in CONSISTENCIA_PESSOA.items():
            comparar(campo, tipos, membros, cpf)
    return grupos, faltas


# ---------------------------------------------------------------------------------------------
# Fórmula comum aos três níveis
# ---------------------------------------------------------------------------------------------
NA = "nao_se_aplica"


def _avaliar(escopo, campos, ref, grupos, faltas, completude=(), validade=True, escondido=lambda t: False,
             nao_analisados=()):
    pend = [{"criterio": "geral", "documento": d["id"], "tipo": d.get("tipo"), "motivo": d["motivo"]}
            for d in nao_analisados]
    prov = bool(nao_analisados)
    itens = {}  # critério -> NA | None (pendente) | (bons, ruins)
    ids = {d["id"] for d in escopo}

    if completude:
        presentes = {d["tipo"] for d in escopo}
        bons, ruins = 0, []
        for t in completude:
            if t in presentes:
                bons += 1
            elif escondido(t):  # pode estar num documento não identificado ou ainda sem empresa
                prov = True
                pend.append({"criterio": "completude", "documento": None, "tipo": t,
                             "motivo": "obrigatório não encontrado, mas há documento não identificado"})
            else:
                ruins.append({"documento": None, "tipo": t, "regra": "obrigatorio_ausente",
                              "detalhe": f"documento obrigatório '{t}' não foi enviado"})
        itens["completude"] = (bons, ruins) if bons + len(ruins) else None
    else:
        itens["completude"] = NA

    if validade and escopo:
        bons, ruins, dispensados = 0, [], 0
        for d in escopo:
            regra = VALIDADE.get(d["tipo"])
            if not regra:
                continue
            c = campos.get(d["id"], {})
            if "nao_aplica" in regra and str(c.get(regra["nao_aplica"][0], "")).lower() == regra["nao_aplica"][1]:
                dispensados += 1
                continue
            base = parse_data(c.get(regra["campo"]))
            if base is None:
                pend.append({"criterio": "validade", "documento": d["id"], "tipo": d["tipo"],
                             "motivo": f"campo '{regra['campo']}' ausente ou ilegível"})
                continue
            venc = _somar_meses(base, regra["prazo_meses"]) if "prazo_meses" in regra else base
            if ref <= venc:  # vence hoje ainda vale
                bons += 1
            else:
                ruins.append({"documento": d["id"], "tipo": d["tipo"], "regra": "documento_vencido",
                              "detalhe": f"venceu em {venc.isoformat()} (referência {ref.isoformat()})"})
        itens["validade"] = (bons, ruins) if bons + len(ruins) else (NA if dispensados and not any(
            p["criterio"] == "validade" for p in pend) else None)
    else:
        itens["validade"] = NA

    if escopo:
        pend += [{"criterio": "consistencia", "documento": d["id"], "tipo": d["tipo"], "motivo": m}
                 for d, _, m in faltas if d["id"] in ids]
        bons, ruins = 0, []
        for g in grupos:
            if not g["docs"] & ids:
                continue
            if not g["divergente"]:
                bons += 1
                continue
            r = {"documento": g.get("documento"), "tipo": g.get("tipo"), "regra": g.get("regra", "campo_divergente"),
                 "campo": g["campo"], "conferir": True,
                 "detalhe": g.get("detalhe", f"valores diferentes para '{g['campo']}'"), "valores": g["valores"]}
            if "cnpj_extraido" in g:
                r["cnpj_extraido"], r["cnpj_contrato"] = g["cnpj_extraido"], g["cnpj_contrato"]
            if g["chave"]:
                r["cpf"] = g["chave"]
            ruins.append(r)
        itens["consistencia"] = (bons, ruins) if bons + len(ruins) else None
    else:
        itens["consistencia"] = NA

    calculados = {c: v for c, v in itens.items() if isinstance(v, tuple)}
    for c, v in itens.items():
        if v is None:
            prov = True
            pend.append({"criterio": c, "documento": None, "tipo": None,
                         "motivo": "nada analisável neste critério; peso redistribuído"})
    soma_pesos = sum(PESOS[c] for c in calculados)
    criterios, descontos, bruto = {}, [], 0.0
    for c in PESOS:
        if c not in calculados:
            criterios[c] = {"peso": PESOS[c], "peso_efetivo": None, "nota": None,
                            "pendente": itens[c] is None, "aplicavel": itens[c] is not NA}
            continue
        bons, ruins = calculados[c]
        total = bons + len(ruins)
        peso_ef = PESOS[c] * 100 / soma_pesos
        bruto += peso_ef * bons / total
        criterios[c] = {"peso": PESOS[c], "peso_efetivo": round(peso_ef, 4), "nota": round(bons / total, 4),
                        "pendente": False, "aplicavel": True, "bons": bons, "ruins": len(ruins)}
        descontos += [{"criterio": c, **r, "pontos": round(peso_ef / total, 4)} for r in ruins]

    res = {"score": None, "score_bruto": None, "classificacao": None, "provisorio": prov, "criterios": criterios,
           "descontos": descontos, "pendencias": pend}
    if calculados:
        score = score_inteiro(bruto)
        res.update(score=score, score_bruto=round(bruto, 4), classificacao=classificar_score(score))
    return res


def calcular_empresa(todos: list[dict], campos: dict, ref: date) -> dict:
    """todos: documentos da empresa (analisados e em_revisao). Só os da PRÓPRIA empresa tornam pendente um
    obrigatório faltante: em_revisao com tipo sugerido conhecido cobre só esse tipo; com tipo desconhecido,
    qualquer faltante. Fora disso o faltante é ausente. Documento sem empresa não entra aqui."""
    docs = [d for d in todos if analisado(d)]
    pendentes = [{**d, "motivo": f"documento não analisado (estado '{d.get('estado')}', tipo '{d.get('tipo')}')"}
                 for d in todos if not analisado(d)]
    grupos, faltas = _grupos_consistencia(docs, campos)

    def escondido(t):
        return any(p["tipo"] not in config.TIPOS or p["tipo"] == t for p in pendentes)

    geral = _avaliar(docs, campos, ref, grupos, faltas, OBRIGATORIOS, True, escondido, pendentes)
    por_tipo = {}
    for t in sorted({d["tipo"] for d in docs} | set(OBRIGATORIOS)):
        possiveis = [p for p in pendentes if p["tipo"] not in config.TIPOS or p["tipo"] == t]
        por_tipo[t] = _avaliar([d for d in docs if d["tipo"] == t], campos, ref, grupos, faltas,
                               (t,) if t in OBRIGATORIOS else (), t in VALIDADE, escondido, possiveis)
    por_doc = {d["id"]: {**_avaliar([d], campos, ref, grupos, faltas, (), d["tipo"] in VALIDADE),
                         "origem_empresa": d.get("origem_empresa")} for d in docs}
    razoes = Counter(campos.get(d["id"], {}).get("razao_social_prestadora") for d in docs)
    razao = next((r for r, _ in razoes.most_common() if r), None)
    return {"razao_social": razao, "documentos_por_tipo": dict(Counter(str(d["tipo"]) for d in todos)), "data_referencia": ref.isoformat(), "geral": geral, "por_tipo": por_tipo,
            "por_documento": por_doc}
