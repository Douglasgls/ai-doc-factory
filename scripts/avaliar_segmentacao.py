"""Compara a segmentação do sistema (via API) com o gabarito anotacoes.csv.

Uso: python scripts/avaliar_segmentacao.py anotacoes.csv [--api http://localhost:8000] [--lote ID_CSV:ID_API ...]
Sem --lote, o lote_id do CSV é usado como id do lote na API.

Métricas por documento (não por página), em cada lote e no total:
- fronteiras: início de documento nas páginas > 1 (a primeira página sempre abre documento, então não conta).
  precisão = fronteiras previstas corretas / fronteiras previstas; recall = / fronteiras do gabarito.
- documentos exatos: fração dos documentos do gabarito cujo (início, fim) aparece idêntico na previsão.
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite importar scripts/ ao rodar direto
from scripts.api_http import abrir  # noqa: E402

VERDADEIRO = {"1", "true", "t", "sim", "s", "yes", "y"}


def ler_gabarito(caminho: str) -> dict[str, list[tuple[int, int]]]:
    """lote_id -> intervalos (ini, fim) dos documentos, a partir de inicio_documento."""
    paginas = defaultdict(list)
    with open(caminho, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            paginas[linha["lote_id"]].append(
                (int(linha["pagina"]), linha["inicio_documento"].strip().lower() in VERDADEIRO))
    gabarito = {}
    for lote, pags in paginas.items():
        pags.sort()
        inicios = [p for p, ini in pags if ini]
        if not inicios or inicios[0] != pags[0][0]:
            inicios.insert(0, pags[0][0])  # a primeira página sempre abre documento
        fins = [i - 1 for i in inicios[1:]] + [pags[-1][0]]
        gabarito[lote] = list(zip(inicios, fins))
    return gabarito


def _razao(a: int, b: int) -> float:
    return a / b if b else 1.0


def _fronteiras(docs: list[tuple[int, int]]) -> set[int]:
    return {ini for ini, _ in docs[1:]}  # docs ordenados: o primeiro não é fronteira


def metricas(real: list[tuple[int, int]], previsto: list[tuple[int, int]]) -> dict:
    fr, fp = _fronteiras(real), _fronteiras(previsto)
    certas = len(fr & fp)
    exatos = len(set(real) & set(previsto))
    return {
        "docs_reais": len(real), "docs_previstos": len(previsto),
        "fronteiras_certas": certas, "fronteiras_previstas": len(fp), "fronteiras_reais": len(fr),
        "precisao": _razao(certas, len(fp)), "recall": _razao(certas, len(fr)),
        "exatos": exatos, "taxa_exatos": _razao(exatos, len(real)),
    }


def somar(ms: list[dict]) -> dict:
    chaves = ("docs_reais", "docs_previstos", "fronteiras_certas", "fronteiras_previstas", "fronteiras_reais", "exatos")
    t = {k: sum(m[k] for m in ms) for k in chaves}
    t["precisao"] = _razao(t["fronteiras_certas"], t["fronteiras_previstas"])
    t["recall"] = _razao(t["fronteiras_certas"], t["fronteiras_reais"])
    t["taxa_exatos"] = _razao(t["exatos"], t["docs_reais"])
    return t


def previsto_da_api(api: str, lote_api: str) -> list[tuple[int, int]]:
    with abrir(f"{api}/lotes/{lote_api}") as r:
        docs = json.load(r)["documentos"]
    return [(d["pagina_ini"], d["pagina_fim"]) for d in docs]


def linha(nome: str, m: dict) -> str:
    return (f"{nome}: docs reais={m['docs_reais']} previstos={m['docs_previstos']} | "
            f"fronteiras precisão={m['precisao']:.3f} recall={m['recall']:.3f} | "
            f"documentos exatos={m['exatos']}/{m['docs_reais']} ({m['taxa_exatos']:.3f})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--lote", action="append", default=[], help="ID_CSV:ID_API")
    args = ap.parse_args()
    mapa = dict(x.split(":", 1) for x in args.lote)
    gabarito = ler_gabarito(args.csv)
    todos = []
    for lote, real in sorted(gabarito.items()):
        m = metricas(real, previsto_da_api(args.api, mapa.get(lote, lote)))
        todos.append(m)
        print(linha(f"lote {lote}", m))
    print(linha("TOTAL", somar(todos)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
