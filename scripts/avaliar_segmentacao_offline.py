"""Avalia a segmentação sem API nem banco: roda app.segmentacao.segmentar sobre o OCR já extraído.

Uso: python scripts/avaliar_segmentacao_offline.py textos_ocr.json anotacoes.csv [--diagnostico]

textos_ocr.json: {lote_id: [texto da página 1, texto da página 2, ...]}.
As métricas são as mesmas de scripts/avaliar_segmentacao.py. Com --diagnostico, cada fronteira errada
(corte a mais ou fronteira perdida) sai com os sinais que a cascata viu: paginação, CNPJ, similaridade
TF-IDF, P(mesmo documento) do Jev e o fim/início das duas páginas.
A faixa ambígua chama o Jev (com cache em disco); com CLASSIFICADOR=regras nada sai para a rede.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite importar app/ e scripts/ ao rodar direto
from app import llm, segmentacao  # noqa: E402
from scripts.avaliar_segmentacao import _fronteiras, ler_gabarito, linha, metricas, somar  # noqa: E402


def _registrar_jev() -> list[float]:
    """Intercepta llm.jev_sim_nao para guardar as probabilidades devolvidas, na ordem das chamadas."""
    probs: list[float] = []
    original = llm.jev_sim_nao

    def espiao(*a, **kw):
        p = original(*a, **kw)
        probs.append(p)
        return p

    llm.jev_sim_nao = espiao
    return probs


def _ref_anterior(textos: list[str], i: int) -> int | None:
    """Índice da última página não branca antes de i (a que a cascata compara com i)."""
    for j in range(i - 1, -1, -1):
        if not segmentacao.em_branco(textos[j]):
            return j
    return None


def diagnostico(lote: str, textos: list[str], pagina: int, especie: str) -> str:
    i = pagina - 1
    ref = _ref_anterior(textos, i)
    partes = [f"--- {lote} pág {pagina}: {especie}"]
    if ref is None:
        return partes[0] + " (sem página anterior com conteúdo)"
    vet = segmentacao._vetores_tfidf(textos)
    sim = segmentacao._cosseno(vet[ref], vet[i])
    partes.append(f"anterior={ref + 1} sim={sim:.3f} paginacao={segmentacao.paginacao(textos[ref])}->"
                  f"{segmentacao.paginacao(textos[i])} cnpj={segmentacao.cnpj(textos[ref])}->{segmentacao.cnpj(textos[i])}")
    partes.append("FIM ANTERIOR: " + repr(textos[ref][-300:]))
    partes.append("INICIO ATUAL: " + repr(textos[i][:300]))
    return "\n".join(partes)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("textos")
    ap.add_argument("csv")
    ap.add_argument("--diagnostico", action="store_true")
    args = ap.parse_args()
    textos = json.loads(Path(args.textos).read_text(encoding="utf-8"))
    gabarito = ler_gabarito(args.csv)
    probs = _registrar_jev()
    todos, erros = [], []
    for lote, real in sorted(gabarito.items()):
        antes = len(probs)
        docs = segmentacao.segmentar(textos[lote])
        previsto = [(d.pagina_ini, d.pagina_fim) for d in docs]
        m = metricas(real, previsto)
        todos.append(m)
        print(linha(f"lote {lote}", m))
        if args.diagnostico:
            fr, fp = _fronteiras(real), _fronteiras(previsto)
            ambiguos = {d.pagina_ini for d in docs if d.ambiguo}
            for p in sorted(fp - fr):
                erros.append(diagnostico(lote, textos[lote], p, "CORTE A MAIS" + (" (ambíguo)" if p in ambiguos else "")))
            for p in sorted(fr - fp):
                erros.append(diagnostico(lote, textos[lote], p, "FRONTEIRA PERDIDA"))
            if probs[antes:]:
                erros.append(f"    {lote}: P(mesmo documento) do Jev, na ordem: {[round(p, 3) for p in probs[antes:]]}")
    print(linha("TOTAL", somar(todos)))
    if args.diagnostico:
        print("\n".join(erros))
    return 0


if __name__ == "__main__":
    sys.exit(main())
