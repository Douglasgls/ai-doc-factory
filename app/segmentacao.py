"""Segmentação de lote em documentos: lista de textos por página -> documentos. Regras locais primeiro; o Jev só
entra na faixa ambígua e para vetar uma continuação esperada."""
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass

from app import config, llm, prompts
from app.anonimizacao import anonimizar_texto
from app.conformidade import validar_cnpj, validar_cpf

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


_FECHO = re.compile(config.SEG_FECHO_REGEX, re.IGNORECASE)

# CPF pontuado (000.000.000-00), tolerando vírgula no lugar do ponto e espaços do OCR; não começa no meio de outro número.
_CPF = re.compile(r"(?<![\d.,/\-])\d{3}[ \t]?[.,][ \t]?\d{3}[ \t]?[.,][ \t]?\d{3}[ \t]?[-–—][ \t]?\d{2}(?!\d)")


def cpfs(texto: str) -> set[str]:
    """CPFs distintos da página com dígitos verificadores corretos (só os 11 dígitos). Um CPF lido errado pelo OCR
    quase nunca fecha os dígitos verificadores, então não vira 'outra pessoa'. Nunca levanta."""
    try:
        return {v for v in (validar_cpf(m) for m in _CPF.findall(texto)) if v}
    except Exception:  # defensivo: um texto estranho não pode derrubar o lote
        log.warning("falha ao extrair CPF; ignorando")
        return set()


def outra_pessoa(anterior: str, atual: str) -> bool:
    """As duas páginas são de documento individual (exatamente um CPF válido em cada) e os CPFs são diferentes.
    Página com vários CPFs (folha de pagamento, lista) ou sem CPF não entra: ali o CPF não identifica o titular."""
    a, b = cpfs(anterior), cpfs(atual)
    return len(a) == 1 and len(b) == 1 and a != b


def fechado(texto: str) -> bool:
    """A página traz a linha de total geral (config.SEG_FECHO_REGEX), que encerra uma tabela: folha de pagamento,
    relação de empregados. O que vem depois, com conteúdo próprio, é outro documento."""
    return _FECHO.search(texto) is not None


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


def residual(texto: str, anterior: str) -> bool:
    """Página residual: pouquíssimo texto (até SEG_RESIDUAL_MAX_ALNUM caracteres alfanuméricos) e quase todas as suas
    palavras (>= SEG_RESIDUAL_CONTIDO) já aparecem na página anterior. É o rabo de um documento: folha só com os campos
    de assinatura sob o cabeçalho corrido, ou a última linha de uma tabela. Um documento novo, mesmo curto, traz
    palavras próprias (outro nome, outro título). Só palavras de 3+ letras contam; números e ruído de OCR não."""
    if sum(c.isalnum() for c in texto) > config.SEG_RESIDUAL_MAX_ALNUM:
        return False
    palavras = {t for t in _tokens(texto) if len(t) >= 3 and t.isalpha()}
    if not palavras:
        return False
    return len(palavras & set(_tokens(anterior))) / len(palavras) >= config.SEG_RESIDUAL_CONTIDO


def prob_mesmo_documento(anterior: str, atual: str) -> float | None:
    """P('a página atual continua o documento da anterior'), do Sim/Não 'noul' do Jev; None = LLM indisponível.

    Recebe o texto inteiro das duas páginas e envia só três trechos: o começo e o fim da anterior e o começo da
    atual (config.SEG_LLM_CABECALHO / SEG_LLM_TRECHO). O começo da anterior deixa o Jev comparar os cabeçalhos.
    Nunca levanta por falha do LLM. Faz chamada de rede: não chamar dentro de transação de banco.
    """
    if config.CLASSIFICADOR == "regras":
        return None  # modo sem rede: nenhum trecho do documento sai do sistema
    # dados pessoais não saem: só as fatias enviadas ao LLM são anonimizadas (as regras locais usam o texto original)
    estado = {"pagina_anterior": {"inicio": anonimizar_texto(anterior[:config.SEG_LLM_CABECALHO]),
                                  "fim": anonimizar_texto(anterior[-config.SEG_LLM_TRECHO:])},
              "pagina_atual": {"inicio": anonimizar_texto(atual[:config.SEG_LLM_TRECHO])}}
    try:
        return llm.jev_sim_nao(estado, prompts.PERGUNTA_FRONTEIRA, prompts.CRITERIOS_FRONTEIRA)
    except llm.LLMErro as e:
        log.warning("fronteira: LLM indisponível (%s); mantendo ambíguo", e)
        return None


def perguntar_llm_mesmo_documento(anterior: str, atual: str) -> bool | None:
    """Faixa ambígua: 'estas duas páginas pertencem ao mesmo documento?' (ver prob_mesmo_documento).

    True = continua; False = abre documento novo; None = meio da faixa ou LLM indisponível (o chamador abre
    documento novo e marca ambiguo=True). Os limiares são decididos aqui, em código (config.SEG_LLM_*).
    """
    p = prob_mesmo_documento(anterior, atual)
    if p is None:
        return None
    if p >= config.SEG_LLM_CONTINUA:
        return True
    if p <= config.SEG_LLM_ABRE:
        return False
    return None


def _continuacao_esperada(anterior: str, atual: str) -> tuple[bool, bool, str]:
    """A página atual tem um sinal próprio de que continua o documento (ver _sem_paginacao). O Jev só veta: abre se
    ele disser com clareza que é outro documento (P <= SEG_LLM_ABRE); na faixa do meio continua e marca o documento
    como ambíguo para a revisão. Sem LLM não há quem vete: abre e marca ambíguo, como na faixa ambígua comum."""
    p = prob_mesmo_documento(anterior, atual)
    if p is None:
        return True, True, "abre (ambíguo): continuação esperada, mas sem Jev para confirmar"
    if p <= config.SEG_LLM_ABRE:
        return True, False, "abre: continuação esperada, mas o Jev vê outro documento"
    if p >= config.SEG_LLM_CONTINUA:
        return False, False, "continua: continuação esperada, confirmada pelo Jev"
    return False, True, "continua (ambíguo): continuação esperada, Jev indeciso"


def _sem_paginacao(anterior: str, atual: str, sim: float, cnpj_ant: str | None, cnpj_atu: str | None,
                   prometida: bool = False) -> tuple[bool, bool, str]:
    """Decide a página `atual` (sem 'Página k de N' legível) contra a última página com conteúdo do documento
    corrente. `prometida`: o documento corrente anunciou mais páginas ('Página k de N' com k < N) e elas ainda não
    chegaram. Devolve (abre, ambíguo, regra que decidiu); a regra é texto para diagnóstico. Com abre=False,
    ambíguo=True quer dizer 'continuou sem certeza': o documento corrente é marcado para a revisão."""
    conhecidos = cnpj_ant is not None and cnpj_atu is not None
    if conhecidos and cnpj_ant != cnpj_atu and validar_cnpj(cnpj_ant) and validar_cnpj(cnpj_atu):
        return True, False, "abre: CNPJs válidos diferentes"  # duas empresas reais: abre mesmo com similaridade alta
    if outra_pessoa(anterior, atual):
        return True, False, "abre: CPFs diferentes"  # mesmo modelo, outra pessoa: abre mesmo com similaridade alta
    if fechado(anterior) and not residual(atual, anterior):
        return True, False, "abre: página anterior fechou a tabela (total geral)"  # mesmo cabeçalho, outra tabela
    if sim >= config.SEG_SIM_ALTO:
        return False, False, f"continua: similaridade alta ({sim:.2f})"
    if residual(atual, anterior):
        return False, False, "continua: página residual"  # folha de assinaturas ou rabo de tabela, sem perguntar
    if prometida or fechado(atual):
        # o documento anunciou esta página ('Página k de N', k < N, e a paginação daqui não foi lida), ou a linha de
        # total geral está aqui e a página anterior não fechou tabela nenhuma: é o fim da tabela que vinha
        return _continuacao_esperada(anterior, atual)
    if sim < config.SEG_SIM_BAIXO and not (conhecidos and cnpj_ant == cnpj_atu):
        return True, False, f"abre: similaridade baixa ({sim:.2f})"
    # faixa ambígua, ou similaridade baixa com o MESMO CNPJ (ex.: tabela contínua)
    mesmo = perguntar_llm_mesmo_documento(anterior, atual)
    if mesmo is None:
        return True, True, f"abre (ambíguo): Jev sem resposta decisiva (sim {sim:.2f})"
    return (not mesmo), False, f"{'continua' if mesmo else 'abre'}: Jev (sim {sim:.2f})"


def segmentar(textos: list[str], decisoes: list | None = None) -> list[Documento]:
    """Cascata: branco/carimbo herda -> 'Página k de N' (k>1 só continua se coerente com a última página paginada do
    documento: mesmo N e k maior; senão abre e marca ambíguo) -> regras sem paginação (_sem_paginacao).

    Sem paginação legível, nesta ordem:
    1. dois CNPJs válidos (dígitos verificadores) e diferentes abrem, mesmo com similaridade alta. CNPJ que não fecha
       os dígitos é erro de OCR, não outra empresa;
    2. um CPF válido em cada página, diferentes, abrem, mesmo com similaridade alta: mesma empresa e mesmo modelo,
       outra pessoa (outra_pessoa);
    3. página anterior com a linha de total geral fechou a tabela: a atual abre, salvo se for residual (fechado);
    4. similaridade alta continua; página residual continua (residual);
    5. continuação esperada (o documento anunciou a página por 'Página k de N' com k < N, ou a linha de total geral
       está na página atual): continua, e o Jev só veta (_continuacao_esperada);
    6. similaridade baixa abre, exceto com o mesmo CNPJ, que vai para a pergunta ao Jev junto com a faixa ambígua;
       sem resposta decisiva, abre e marca ambíguo.

    `decisoes`, se passado, recebe (página 1-based, regra que decidiu) de cada página com conteúdo depois da primeira:
    só diagnóstico (scripts/avaliar_segmentacao_offline.py --diagnostico)."""
    if not textos:
        return []

    def nota(i: int, regra: str) -> None:
        if decisoes is not None:
            decisoes.append((i + 1, regra))  # (página 1-based, regra que decidiu): só diagnóstico
    vetores = _vetores_tfidf(textos)
    cnpjs = [cnpj(t) for t in textos]
    inicios: list[tuple[int, bool]] = [(0, False)]  # (índice da página, ambíguo)
    ref = None  # última página não vazia do documento corrente
    pag_doc = None  # (k, N) da última página paginada do documento corrente; None = sem paginação conhecida
    faltam = 0  # páginas que o documento corrente ainda anunciou: N - k, menos as que continuaram sem paginação legível
    if not em_branco(textos[0]):
        ref = 0
        pag_doc = paginacao(textos[0])
        faltam = pag_doc[1] - pag_doc[0] if pag_doc else 0
    for i in range(1, len(textos)):
        texto = textos[i]
        if em_branco(texto):
            continue  # herda o documento anterior (também vale para verso em branco)
        if ref is None:
            # documento corrente só tem páginas em branco (início do lote): o conteúdo as absorve
            ref = i
            pag_doc = paginacao(texto)
            faltam = pag_doc[1] - pag_doc[0] if pag_doc else 0
            continue
        pag = paginacao(texto)
        if pag is not None and pag[0] == 1:
            inicios.append((i, False))
            pag_doc = pag
            faltam = pag[1] - pag[0]
            nota(i, "abre: página 1 de N")
        elif pag is not None and pag[0] > 1:
            if pag_doc is None or (pag[1] == pag_doc[1] and pag[0] > pag_doc[0]):
                # continua: sem paginação conhecida no documento, ou k avança com o mesmo N (salto tolerado)
                nota(i, "continua: página k de N")
            else:
                # incoerente (N diferente, k não avança ou documento já completo): a primeira página do outro
                # documento se perdeu; abre e marca ambíguo para a revisão
                inicios.append((i, True))
                nota(i, "abre (ambíguo): página k de N incoerente")
            pag_doc = pag
            faltam = pag[1] - pag[0]
        else:
            abre, ambiguo, regra = _sem_paginacao(textos[ref], texto, _cosseno(vetores[ref], vetores[i]),
                                                  cnpjs[ref], cnpjs[i], prometida=faltam > 0)
            nota(i, regra)
            if abre:
                inicios.append((i, ambiguo))
                pag_doc = None  # documento novo sem paginação legível: não herda a do anterior
                faltam = 0
            else:
                faltam = max(0, faltam - 1)  # esta página conta como uma das anunciadas
                if ambiguo:
                    inicios[-1] = (inicios[-1][0], True)  # continuou sem certeza: o documento vai para a revisão
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
