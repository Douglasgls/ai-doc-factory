"""Segmentação de lote em documentos, sem LLM. Função pura: lista de textos por página -> documentos."""
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from app import config, llm, prompts
from app.anonimizacao import anonimizar_texto
from app.conformidade import validar_cnpj

log = logging.getLogger(__name__)

# "Página 1 de 3", tolerando caixa, espaços, "Pag."/"Pág", "1/3" e confusões comuns do OCR (l/I/|/O no lugar de 1/0).
_PAGINACAO = re.compile(r"\bp[aá4]g(?:ina|\.)?\s*([0-9lLiI|oO]{1,3})\s*(?:de|/)\s*([0-9lLiI|oO]{1,3})(?!\w)", re.IGNORECASE)
_TOKEN = re.compile(r"\w{2,}")


@dataclass(frozen=True)
class Documento:
    pagina_ini: int  # 1-based, inclusivo
    pagina_fim: int
    ambiguo: bool = False


def _num(s: str) -> int:
    return int(s.translate(str.maketrans("lLiI|oO", "1111100")))


def paginacao(texto: str) -> tuple[int, int] | None:
    """(k, N) da última ocorrência de 'Página k de N' em cabeçalho ou rodapé, ou None.

    Só conta ocorrência nas primeiras ou últimas config.SEG_PAG_LINHAS linhas não vazias da página; uma frase
    no corpo ("conforme página 1 de 3 do contrato") é ignorada."""
    linhas = [ln for ln in texto.splitlines() if ln.strip()]
    n_lin = config.SEG_PAG_LINHAS
    if len(linhas) > 2 * n_lin:
        blocos = ["\n".join(linhas[:n_lin]), "\n".join(linhas[-n_lin:])]  # cabeçalho, rodapé
    else:
        blocos = ["\n".join(linhas)]
    # a regex aceita quebra de linha dentro da expressão ("Página 1\nde 3"); vale a última ocorrência
    achados = [a for b in blocos for a in _PAGINACAO.findall(b)]
    if not achados:
        return None
    k, n = achados[-1]
    k, n = _num(k), _num(n)
    if k < 1 or n < 1 or k > n:
        return None  # paginação impossível: cai na cascata TF-IDF
    return k, n


def em_branco(texto: str) -> bool:
    """Página sem conteúdo: ruído de scanner (< 3 caracteres alfanuméricos) ou só um carimbo curto
    (até SEG_BRANCO_MAX_ALNUM, ex.: 'PROTOCOLADO'). Página com 'Página k de N' nunca é branca, porque
    isso é conteúdo de documento. O texto continua gravado na página (busca); só a segmentação o ignora."""
    n = sum(c.isalnum() for c in texto)
    if n < 3:
        return True
    return n <= config.SEG_BRANCO_MAX_ALNUM and paginacao(texto) is None


# CNPJ tolerante a OCR: separadores trocados, ausentes ou duplicados entre os grupos 2.3.3/4-2.
_CNPJ = re.compile(r"(?<!\d)(\d{2})[^\d\n]{0,2}(\d{3})[^\d\n]{0,2}(\d{3})[^\d\n]{0,3}(\d{4})[^\d\n]{0,3}(\d{2})(?!\d)")


def cnpj(texto: str) -> str | None:
    """Primeiro CNPJ do texto, só com os 14 dígitos, ou None. Nunca levanta."""
    try:
        m = _CNPJ.search(texto)
        return "".join(m.groups()) if m else None
    except Exception:  # defensivo: um texto estranho não pode derrubar o lote
        log.warning("falha ao extrair CNPJ; ignorando")
        return None


def _tokens(texto: str) -> Counter:
    return Counter(_TOKEN.findall(texto.lower()))


def _vetores_tfidf(textos: list[str]) -> list[dict[str, float]]:
    contagens = [_tokens(t) for t in textos]
    df = Counter(tok for c in contagens for tok in c)
    n = len(textos)
    vetores = []
    for c in contagens:
        v = {tok: (1 + math.log(f)) * (math.log((1 + n) / (1 + df[tok])) + 1) for tok, f in c.items()}
        norma = math.sqrt(sum(x * x for x in v.values())) or 1.0
        vetores.append({tok: x / norma for tok, x in v.items()})
    return vetores


def _cosseno(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(tok, 0.0) for tok, x in a.items())


def perguntar_llm_mesmo_documento(fim_anterior: str, inicio_atual: str) -> bool | None:
    """Faixa ambígua: 'estas duas páginas pertencem ao mesmo documento?' (Sim/Não 'noul' do Jev).

    True = continua; False = abre documento novo; None = meio da faixa ou LLM indisponível (o chamador abre
    documento novo e marca ambiguo=True). Os limiares são decididos aqui, em código (config.SEG_LLM_*).
    Nunca levanta por falha do LLM. Faz chamada de rede: não chamar dentro de transação de banco.
    """
    if config.CLASSIFICADOR == "regras":
        return None  # modo sem rede: nenhum trecho do documento sai do sistema
    # dados pessoais não saem: só as fatias enviadas ao LLM são anonimizadas (as regras locais usam o texto original)
    estado = {"pagina_anterior": {"fim": anonimizar_texto(fim_anterior)},
              "pagina_atual": {"inicio": anonimizar_texto(inicio_atual)}}
    try:
        p = llm.jev_sim_nao(estado, prompts.PERGUNTA_FRONTEIRA, prompts.CRITERIOS_FRONTEIRA)
    except llm.LLMErro as e:
        log.warning("fronteira: LLM indisponível (%s); mantendo ambíguo", e)
        return None
    if p >= config.SEG_LLM_CONTINUA:
        return True
    if p <= config.SEG_LLM_ABRE:
        return False
    return None


def segmentar(textos: list[str]) -> list[Documento]:
    """Cascata: branco/carimbo herda -> 'Página k de N' (k>1 só continua se coerente com a última página paginada do
    documento: mesmo N e k maior; senão abre e marca ambíguo) -> CNPJ + TF-IDF -> ambíguo (Jev; sem resposta abre e marca).

    Sem paginação: dois CNPJs válidos (dígitos verificadores) e diferentes abrem documento, mesmo com similaridade
    alta (sem perguntar ao Jev); com similaridade alta e algum CNPJ inválido (provável erro de OCR), continua.
    Abaixo da similaridade alta, CNPJ diferente abre; similaridade baixa abre, exceto com o mesmo CNPJ, que vai
    para a pergunta ao Jev junto com a faixa ambígua."""
    if not textos:
        return []
    vetores = _vetores_tfidf(textos)
    cnpjs = [cnpj(t) for t in textos]
    inicios: list[tuple[int, bool]] = [(0, False)]  # (índice da página, ambíguo)
    ref = None  # última página não vazia do documento corrente
    pag_doc = None  # (k, N) da última página paginada do documento corrente; None = sem paginação conhecida
    if not em_branco(textos[0]):
        ref = 0
        pag_doc = paginacao(textos[0])
    for i in range(1, len(textos)):
        texto = textos[i]
        if em_branco(texto):
            continue  # herda o documento anterior (também vale para verso em branco)
        if ref is None:
            # documento corrente só tem páginas em branco (início do lote): o conteúdo as absorve
            ref = i
            pag_doc = paginacao(texto)
            continue
        pag = paginacao(texto)
        if pag is not None and pag[0] == 1:
            inicios.append((i, False))
            pag_doc = pag
        elif pag is not None and pag[0] > 1:
            if pag_doc is None or (pag[1] == pag_doc[1] and pag[0] > pag_doc[0]):
                pass  # continua: sem paginação conhecida no documento, ou k avança com o mesmo N (salto tolerado)
            else:
                # incoerente (N diferente, k não avança ou documento já completo): a primeira página do outro
                # documento se perdeu; abre e marca ambíguo para a revisão
                inicios.append((i, True))
            pag_doc = pag
        else:
            abertos = len(inicios)
            sim = _cosseno(vetores[ref], vetores[i])
            conhecidos = cnpjs[ref] is not None and cnpjs[i] is not None
            if conhecidos and cnpjs[ref] != cnpjs[i] and validar_cnpj(cnpjs[ref]) and validar_cnpj(cnpjs[i]):
                inicios.append((i, False))  # duas empresas reais diferentes: abre mesmo com similaridade alta
            elif sim >= config.SEG_SIM_ALTO:
                pass
            elif conhecidos and cnpjs[ref] != cnpjs[i]:
                inicios.append((i, False))  # outra empresa: abre, sem perguntar
            elif sim < config.SEG_SIM_BAIXO and not (conhecidos and cnpjs[ref] == cnpjs[i]):
                inicios.append((i, False))
            else:  # faixa ambígua, ou similaridade baixa com o MESMO CNPJ (ex.: tabela contínua)
                mesmo = perguntar_llm_mesmo_documento(textos[ref][-500:], texto[:500])
                if mesmo is None:
                    inicios.append((i, True))
                elif not mesmo:
                    inicios.append((i, False))
            if len(inicios) > abertos:
                pag_doc = None  # documento novo sem paginação legível: não herda a do anterior
        ref = i
    docs = []
    for j, (ini, amb) in enumerate(inicios):
        fim = inicios[j + 1][0] if j + 1 < len(inicios) else len(textos)
        docs.append(Documento(ini + 1, fim, amb))
    reconciliar(docs, len(textos))
    return docs


def reconciliar(docs: list[Documento], total: int) -> None:
    """Toda página em exatamente um documento: sem buracos e sem sobreposição."""
    esperado = 1
    for d in docs:
        assert d.pagina_ini == esperado, f"buraco ou sobreposição em {d}: esperado início {esperado}"
        assert d.pagina_fim >= d.pagina_ini, f"intervalo invertido em {d}"
        esperado = d.pagina_fim + 1
    assert esperado == total + 1, f"páginas sem documento: cobertas {esperado - 1} de {total}"
