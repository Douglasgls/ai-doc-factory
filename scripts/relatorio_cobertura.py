"""Curva cobertura x precisão por limiar, por documento, cruzando GET /lotes/{id} com anotacoes.csv.

Uso: python scripts/relatorio_cobertura.py anotacoes.csv [--api http://localhost:8000]
         [--lote ID_CSV:ID_API ...] [--limiar 0.5 --limiar 0.85 ...]

Para cada limiar t, um documento é "automático" se o roteamento real (app.roteamento.decidir, com CONF_AUTO=t
e CONF_MIN do ambiente) o classifica sem revisão; os demais vão para revisão. Isso inclui segmentação ambígua e
sugestão `nenhum_dos_anteriores` ou tipo `desconhecido`, que vão para revisão em qualquer limiar. Limitação: a API
não expõe a segunda opinião do Gemini, então o desacordo entre modelos não entra nesta simulação. Reporta % automático, precisão na parte automática (tipo sugerido == tipo do gabarito) e
% em revisão. O tipo sugerido vem do argmax das probabilidades do classificador (não do campo `tipo`, que já
passou pelo roteamento e pela correção humana). O tipo real de um documento é o mais frequente entre as
páginas dele no gabarito. Documentos ainda não classificados (sem confiança) são ignorados e contados.

Os números dependem do classificador e dos lotes usados: este script só mede, não valida o sistema.
"""
import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite importar app/ ao rodar o script direto
from app import config  # noqa: E402
from app.roteamento import decidir  # noqa: E402
from scripts.api_http import abrir  # noqa: E402

LIMIARES_PADRAO = (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95)


def ler_tipos_paginas(caminho: str) -> dict[str, dict[int, str]]:
    """lote_id -> {pagina: tipo}, a partir do gabarito."""
    tipos = defaultdict(dict)
    with open(caminho, newline="", encoding="utf-8") as f:
        for linha in csv.DictReader(f):
            tipos[linha["lote_id"]][int(linha["pagina"])] = linha["tipo"].strip()
    return dict(tipos)


def tipo_real(paginas: dict[int, str], ini: int, fim: int) -> str | None:
    cont = Counter(paginas[p] for p in range(ini, fim + 1) if p in paginas)
    return cont.most_common(1)[0][0] if cont else None


NENHUM = "nenhum_dos_anteriores"


def tipo_sugerido(doc: dict) -> str | None:
    """Argmax das probabilidades; `nenhum_dos_anteriores` (ou tipo já `desconhecido`) vira `desconhecido`."""
    probs = doc.get("probabilidades") or {}
    if doc.get("tipo") == config.TIPO_DESCONHECIDO:
        return config.TIPO_DESCONHECIDO
    if probs and max(probs.values()) > 0:
        # desempate estável: a probabilidade vem arredondada, então empata com frequência
        melhor = max(probs, key=lambda t: (probs[t], t))
        return config.TIPO_DESCONHECIDO if melhor == NENHUM else melhor
    return None  # sem probabilidades úteis (ex.: nenhuma palavra-chave): conta como erro se for automático


def rotular(paginas: dict[int, str], docs_api: list[dict]) -> tuple[list[tuple], int]:
    """(confianca, correto, ambiguo, sugerido) por documento classificado, e quantos foram ignorados."""
    itens, ignorados = [], 0
    for d in docs_api:
        real = tipo_real(paginas, d["pagina_ini"], d["pagina_fim"])
        if d.get("confianca") is None or real is None:
            ignorados += 1
            continue
        sugerido = tipo_sugerido(d)
        itens.append((d["confianca"], sugerido == real, bool(d.get("segmentacao_ambigua")), sugerido))
    return itens, ignorados


def curva(itens: list[tuple], limiares) -> list[dict]:
    n = len(itens)
    saida = []
    original = config.CONF_AUTO
    try:
        return _curva(itens, limiares, n, saida)
    finally:
        config.CONF_AUTO = original


def _curva(itens, limiares, n, saida) -> list[dict]:
    for t in limiares:
        config.CONF_AUTO = t  # decidir() lê o limiar de config a cada chamada
        auto = [correto for conf, correto, amb, sug in itens
                if decidir(conf, sug, segmentacao_ambigua=amb).estado == "classificado"]
        saida.append({
            "limiar": t, "documentos": n, "automaticos": len(auto), "corretos": sum(auto),
            "pct_automatico": len(auto) / n if n else 0.0,
            "precisao_automatico": sum(auto) / len(auto) if auto else None,
            "pct_revisao": (n - len(auto)) / n if n else 0.0,
        })
    return saida


def imprimir(linhas: list[dict]) -> None:
    print(f"{'limiar':>7} {'% auto':>8} {'precisão auto':>14} {'% revisão':>10} {'auto/total':>11}")
    for l in linhas:
        prec = "n/d" if l["precisao_automatico"] is None else f"{l['precisao_automatico']:.3f}"
        print(f"{l['limiar']:>7.2f} {l['pct_automatico']:>8.1%} {prec:>14} {l['pct_revisao']:>10.1%} "
              f"{l['automaticos']:>5}/{l['documentos']:<5}")


def docs_da_api(api: str, lote_api: str) -> list[dict]:
    with abrir(f"{api}/lotes/{lote_api}") as r:
        return json.load(r)["documentos"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--lote", action="append", default=[], help="ID_CSV:ID_API")
    ap.add_argument("--limiar", action="append", type=float, help="limiar candidato (repetível)")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # console do Windows usa cp1252 por padrão
    mapa = dict(x.split(":", 1) for x in args.lote)
    itens, ignorados = [], 0
    for lote, paginas in sorted(ler_tipos_paginas(args.csv).items()):
        i, ig = rotular(paginas, docs_da_api(args.api, mapa.get(lote, lote)))
        itens += i
        ignorados += ig
    print(f"documentos avaliados: {len(itens)} (ignorados sem confiança ou sem gabarito: {ignorados})")
    imprimir(curva(itens, sorted(args.limiar or LIMIARES_PADRAO)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
