"""Geração determinística de nomes padronizados de arquivo por tipo documental.

A IA extrai os dados estruturados; este módulo aplica exclusivamente regras
determinísticas, sanitização e validação para compor o nome final do PDF.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date

from app.conformidade import parse_data

DOCUMENT_TEMPLATES: dict[str, list[str]] = {
    "aso": ["nome_funcionario", "data_exame", "tipo_exame"],
    "folha_pagamento": ["nome_empresa", "competencia"],
    "folha_ponto": ["nome_funcionario", "competencia"],
    "holerite": ["nome_funcionario", "competencia"],
    "recibo_ferias": ["nome_funcionario", "inicio_ferias", "fim_ferias"],
    "atestado_medico": ["nome_funcionario", "data_emissao"],
    "contrato_trabalho": ["nome_funcionario", "data_admissao"],
    "aditivo_contratual": ["nome_funcionario", "data_admissao"],
}

TIPOS_EXAME_VALIDOS: dict[str, str] = {
    "admissional": "admissional",
    "periodico": "periodico",
    "retorno_trabalho": "retorno_trabalho",
    "retorno_ao_trabalho": "retorno_trabalho",
    "mudanca_risco": "mudanca_risco",
    "mudanca_de_risco": "mudanca_risco",
    "mudanca_de_risco_ocupacional": "mudanca_risco",
    "demissional": "demissional",
}

_MESES_PT: dict[str, int] = {
    "jan": 1, "janeiro": 1,
    "fev": 2, "fevereiro": 2,
    "mar": 3, "marco": 3,
    "abr": 4, "abril": 4,
    "mai": 5, "maio": 5,
    "jun": 6, "junho": 6,
    "jul": 7, "julho": 7,
    "ago": 8, "agosto": 8,
    "set": 9, "setembro": 9,
    "out": 10, "outubro": 10,
    "nov": 11, "novembro": 11,
    "dez": 12, "dezembro": 12,
}

_RE_COMPETENCIA_ISO = re.compile(r"^\s*(\d{4})[-/](\d{1,2})\s*$")
_RE_COMPETENCIA_BR = re.compile(r"^\s*(\d{1,2})[-/](\d{4})\s*$")
_RE_COMPETENCIA_EXTENSO = re.compile(r"^\s*([a-z]+)\s*(?:de\s*|[/\-]\s*)?(\d{4})\s*$")


def slugificar(texto: str) -> str:
    """Converte texto livre para snake_case ASCII minúsculo seguro para nome de arquivo."""
    if not texto:
        return ""
    normalizado = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(ch for ch in normalizado if not unicodedata.combining(ch))
    minusculo = sem_acentos.lower()
    apenas_seguros = re.sub(r"[^a-z0-9]+", "_", minusculo)
    return apenas_seguros.strip("_")


def normalizar_data_iso(valor: str | None) -> str | None:
    """Valida uma data e retorna no formato ISO AAAA-MM-DD, ou None se inválida."""
    if not valor or not isinstance(valor, str):
        return None
    d: date | None = parse_data(valor.strip())
    return d.isoformat() if d is not None else None


def normalizar_competencia(valor: str | None) -> str | None:
    """Normaliza competência (ex.: '2026-03', '03/2026', 'Março de 2026') para AAAA-MM."""
    if not valor or not isinstance(valor, str):
        return None
    bruto = slugificar(valor).replace("_", " ").strip()
    limpo = valor.strip()

    m = _RE_COMPETENCIA_ISO.match(limpo)
    if m:
        ano, mes = int(m.group(1)), int(m.group(2))
        if 1900 <= ano <= 2100 and 1 <= mes <= 12:
            return f"{ano:04d}-{mes:02d}"

    m = _RE_COMPETENCIA_BR.match(limpo)
    if m:
        mes, ano = int(m.group(1)), int(m.group(2))
        if 1900 <= ano <= 2100 and 1 <= mes <= 12:
            return f"{ano:04d}-{mes:02d}"

    m = _RE_COMPETENCIA_EXTENSO.match(bruto)
    if m:
        mes = _MESES_PT.get(m.group(1))
        ano = int(m.group(2))
        if mes is not None and 1900 <= ano <= 2100:
            return f"{ano:04d}-{mes:02d}"

    # Fallback: data completa (ex.: 2026-03-01) -> AAAA-MM
    d = parse_data(limpo)
    if d is not None:
        return f"{d.year:04d}-{d.month:02d}"
    return None


def normalizar_tipo_exame(valor: str | None) -> str | None:
    """Normaliza a natureza do exame do ASO para os valores padronizados."""
    if not valor or not isinstance(valor, str):
        return None
    chave = slugificar(valor)
    if chave in TIPOS_EXAME_VALIDOS:
        return TIPOS_EXAME_VALIDOS[chave]
    for k, destino in TIPOS_EXAME_VALIDOS.items():
        if k in chave:
            return destino
    return None


def _extrair_nome_funcionario(campos: dict[str, str]) -> str | None:
    bruto = campos.get("nome_funcionario") or campos.get("nome")
    s = slugificar(bruto or "")
    return s or None


def _extrair_nome_empresa(campos: dict[str, str], nome_empresa_lote: str | None) -> str | None:
    bruto = (
        campos.get("nome_empresa")
        or campos.get("razao_social_prestadora")
        or nome_empresa_lote
    )
    s = slugificar(bruto or "")
    return s or None


def _periodo_ou_competencia(campos: dict[str, str]) -> str | None:
    """Para folha_ponto: usa competência (AAAA-MM) ou intervalo inicio_a_fim se período parcial."""
    ini = normalizar_data_iso(campos.get("inicio_periodo"))
    fim = normalizar_data_iso(campos.get("fim_periodo"))
    if ini and fim:
        return f"{ini}_a_{fim}"
    return normalizar_competencia(campos.get("competencia"))


def gerar_nome_padronizado(
    tipo: str | None,
    campos: dict[str, str] | None = None,
    *,
    documento_id: int | None = None,
    nome_empresa_lote: str | None = None,
    nome_original: str | None = None,
) -> str:
    """Gera o nome padronizado do documento (sempre minúsculo, ASCII, snake_case, .pdf).

    Inclui apenas informações realmente extraídas e validadas; nunca expõe CPF, RG, PIS ou CID.
    """
    dados = campos or {}
    tipo_slug = slugificar(tipo or "")

    if not tipo_slug:
        if nome_original:
            base = slugificar(nome_original.rsplit(".", 1)[0])
            if base:
                return f"{base}.pdf"
        return f"documento_{documento_id}.pdf" if documento_id is not None else "documento.pdf"

    partes: list[str] = [tipo_slug]

    if tipo_slug == "aso":
        nome = _extrair_nome_funcionario(dados)
        data_exame = normalizar_data_iso(dados.get("data_exame"))
        tipo_exame = normalizar_tipo_exame(dados.get("tipo_exame"))
        if nome:
            partes.append(nome)
        if data_exame:
            partes.append(data_exame)
        if tipo_exame:
            partes.append(tipo_exame)

    elif tipo_slug == "folha_pagamento":
        empresa = _extrair_nome_empresa(dados, nome_empresa_lote)
        comp = normalizar_competencia(dados.get("competencia"))
        if empresa:
            partes.append(empresa)
        if comp:
            partes.append(comp)

    elif tipo_slug == "folha_ponto":
        nome = _extrair_nome_funcionario(dados)
        ref = _periodo_ou_competencia(dados)
        if nome:
            partes.append(nome)
        if ref:
            partes.append(ref)

    elif tipo_slug == "holerite":
        nome = _extrair_nome_funcionario(dados)
        comp = normalizar_competencia(dados.get("competencia"))
        if nome:
            partes.append(nome)
        if comp:
            partes.append(comp)

    elif tipo_slug == "recibo_ferias":
        nome = _extrair_nome_funcionario(dados)
        ini = normalizar_data_iso(dados.get("inicio_ferias"))
        fim = normalizar_data_iso(dados.get("fim_ferias"))
        if nome:
            partes.append(nome)
        if ini and fim:
            partes.append(f"{ini}_a_{fim}")
        elif ini:
            partes.append(ini)

    elif tipo_slug == "atestado_medico":
        nome = _extrair_nome_funcionario(dados)
        data_emissao = normalizar_data_iso(dados.get("data_emissao"))
        if nome:
            partes.append(nome)
        if data_emissao:
            partes.append(data_emissao)

    elif tipo_slug in ("contrato_trabalho", "aditivo_contratual"):
        nome = _extrair_nome_funcionario(dados)
        data_adm = normalizar_data_iso(dados.get("data_admissao"))
        if nome:
            partes.append(nome)
        if data_adm:
            partes.append(data_adm)

    else:
        nome = _extrair_nome_funcionario(dados)
        if nome:
            partes.append(nome)

    # Se nenhum campo complementar foi encontrado além do tipo, usa o ID para evitar nomes genéricos idênticos
    if len(partes) == 1 and documento_id is not None:
        partes.append(str(documento_id))

    return f"{'_'.join(partes)}.pdf"


def resolver_colisoes_nomes(itens: list[tuple[int, str]]) -> dict[int, str]:
    """Desambigua nomes repetidos adicionando sufixo _01, _02... mantendo ordem dos itens.

    Recebe lista de (documento_id, nome_base_pdf) e devolve {documento_id: nome_unico_pdf}.
    """
    contagem: dict[str, int] = {}
    for _, nome in itens:
        contagem[nome] = contagem.get(nome, 0) + 1

    indices: dict[str, int] = {}
    saida: dict[int, str] = {}
    for doc_id, nome in itens:
        if contagem[nome] == 1:
            saida[doc_id] = nome
            continue
        idx = indices.get(nome, 0) + 1
        indices[nome] = idx
        stem = nome[:-4] if nome.endswith(".pdf") else nome
        saida[doc_id] = f"{stem}_{idx:02d}.pdf"
    return saida


def atualizar_nome_padronizado(conn, documento_id: int) -> str | None:
    """Recalcula e persiste `documento.nome_padronizado` a partir dos campos atuais e resolve colisões."""
    row = conn.execute(
        "SELECT d.tipo, d.lote_id, l.nome_arquivo, l.empresa_id, e.nome "
        "FROM documento d "
        "JOIN lote l ON l.id = d.lote_id "
        "LEFT JOIN empresa e ON e.id = l.empresa_id "
        "WHERE d.id = %s",
        (documento_id,),
    ).fetchone()
    if row is None:
        return None
    tipo, lote_id, nome_original, empresa_id, nome_empresa_lote = row
    campos = dict(
        conn.execute(
            "SELECT campo, valor FROM documento_campos WHERE documento_id = %s",
            (documento_id,),
        ).fetchall()
    )
    nome_base = gerar_nome_padronizado(
        tipo,
        campos,
        documento_id=documento_id,
        nome_empresa_lote=nome_empresa_lote,
        nome_original=nome_original,
    )
    stem = nome_base[:-4] if nome_base.endswith(".pdf") else nome_base
    padrao_colisao = f"^{re.escape(stem)}(?:_[0-9]{{2}})?\\.pdf$"

    if empresa_id is not None:
        concorrentes = conn.execute(
            "SELECT d.id, d.nome_padronizado FROM documento d "
            "JOIN lote l ON l.id = d.lote_id "
            "WHERE l.empresa_id = %s AND d.id <> %s AND d.nome_padronizado ~ %s "
            "ORDER BY d.id",
            (empresa_id, documento_id, padrao_colisao),
        ).fetchall()
    else:
        concorrentes = conn.execute(
            "SELECT d.id, d.nome_padronizado FROM documento d "
            "WHERE d.lote_id = %s AND d.id <> %s AND d.nome_padronizado ~ %s "
            "ORDER BY d.id",
            (lote_id, documento_id, padrao_colisao),
        ).fetchall()

    if not concorrentes:
        conn.execute(
            "UPDATE documento SET nome_padronizado = %s WHERE id = %s",
            (nome_base, documento_id),
        )
        return nome_base

    # Garante numeração determinística (_01, _02, ...) entre os documentos com mesma referência
    todos = sorted([(cid, nome_base) for cid, _ in concorrentes] + [(documento_id, nome_base)], key=lambda x: x[0])
    resolvidos = resolver_colisoes_nomes(todos)
    for cid, nome_final in resolvidos.items():
        conn.execute(
            "UPDATE documento SET nome_padronizado = %s WHERE id = %s",
            (nome_final, cid),
        )
    return resolvidos[documento_id]

