"""Baseline do Goal 3: TF-IDF + regressão logística sobre o texto do OCR.

Uso:
  python scripts/baseline_tfidf.py treinar anotacoes_treino.csv --modelo modelo_baseline.joblib \
      --lote L0001:1 --lote L0002:2 ... [--api http://localhost:8000]
  python scripts/baseline_tfidf.py avaliar anotacoes.csv --modelo modelo_baseline.joblib \
      --lote ID_CSV:ID_API ... [--saida-json resultado.json]

Os dois subcomandos buscam o texto OCR por página na API (`GET /lotes/{id}` e `GET /documentos/{id}`).
Os documentos vêm do GABARITO (intervalos de `inicio_documento`, tipo = o mais frequente entre as páginas), e o
texto segue a regra do worker_classify (`app.classificar.montar_texto`: páginas concatenadas, truncadas em 6000
caracteres). Por isso o `avaliar` mede só a classificação, sobre o documento do gabarito, sem depender da
segmentação (diferente de scripts/avaliar_classificacao.py, que usa os documentos previstos). A saída usa o mesmo
formato dele (acurácia, F1 macro, tabela por tipo, matriz de confusão, qualidade).

Dependências: requirements-baseline.txt (scikit-learn, joblib), só no host. Rodar `treinar` só com lotes de
TREINO; o `avaliar` só deve tocar o conjunto de teste na medição final.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite importar app/ e scripts/ ao rodar direto
from app.classificar import montar_texto  # noqa: E402
from scripts.api_http import abrir  # noqa: E402
from scripts.avaliar_classificacao import documentos_reais, imprimir, ler_paginas, por_qualidade, resumo  # noqa: E402
from scripts.avaliar_segmentacao import ler_gabarito  # noqa: E402
from scripts.relatorio_cobertura import docs_da_api  # noqa: E402

SEED = 42


def _get(api: str, caminho: str) -> dict:
    with abrir(f"{api}{caminho}") as r:
        return json.load(r)


def textos_paginas(api: str, lote_api: str) -> dict[int, str]:
    """pagina -> texto OCR de todo o lote, lido dos documentos previstos pela API."""
    textos = {}
    for d in docs_da_api(api, lote_api):
        for p in _get(api, f"/documentos/{d['id']}")["paginas"]:
            textos[p["numero"]] = p.get("texto") or ""
    return textos


def montar_documentos(intervalos, paginas_csv, textos: dict[int, str]) -> list[dict]:
    """Documentos do gabarito com texto: [{ini, fim, tipo, qualidade, texto}]."""
    docs = []
    for r in documentos_reais(intervalos, paginas_csv):
        r["texto"] = montar_texto([textos.get(p, "") for p in range(r["ini"], r["fim"] + 1)])
        docs.append(r)
    return docs


def carregar(api: str, csv: str, mapa: dict[str, str]) -> list[dict]:
    """Documentos (com texto e 'lote') de todos os lotes do mapa ID_CSV -> ID_API."""
    gabarito, paginas = ler_gabarito(csv), ler_paginas(csv)
    docs = []
    for lote in sorted(mapa):
        if lote not in gabarito:
            raise SystemExit(f"lote {lote} não está no CSV")
        for d in montar_documentos(gabarito[lote], paginas[lote], textos_paginas(api, mapa[lote])):
            docs.append({**d, "lote": lote})
    return docs


def novo_pipeline():
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    return make_pipeline(
        TfidfVectorizer(lowercase=True, strip_accents="unicode", ngram_range=(1, 2), sublinear_tf=True, min_df=2),
        LogisticRegression(class_weight="balanced", max_iter=1000, random_state=SEED))


def validacao_cruzada(docs: list[dict], folds: int = 5) -> list[str]:
    """Previsões por GroupKFold (grupo = lote), para sanidade no treino."""
    from sklearn.model_selection import GroupKFold, cross_val_predict
    X, y, g = [d["texto"] for d in docs], [d["tipo"] for d in docs], [d["lote"] for d in docs]
    folds = min(folds, len(set(g)))
    return list(cross_val_predict(novo_pipeline(), X, y, groups=g, cv=GroupKFold(n_splits=folds)))


def linhas_de(docs: list[dict], previstos: list[str]) -> list[dict]:
    return [{"real": d["tipo"], "previsto": p, "exata": True, "qualidade": d["qualidade"]}
            for d, p in zip(docs, previstos)]


def relatorio(titulo: str, linhas: list[dict]) -> dict:
    r = resumo(linhas)
    imprimir(titulo, r)
    print("\npor qualidade: " + " | ".join(f"{q}: {c}/{n} corretos" for q, (n, c) in por_qualidade(linhas).items()))
    return r


def _mapa(lotes: list[str]) -> dict[str, str]:
    if not lotes:
        raise SystemExit("informe ao menos um --lote ID_CSV:ID_API")
    return dict(x.split(":", 1) for x in lotes)


def cmd_treinar(args) -> int:
    import joblib
    docs = carregar(args.api, args.csv, _mapa(args.lote))
    print(f"documentos de treino: {len(docs)} em {len({d['lote'] for d in docs})} lotes")
    modelo = novo_pipeline().fit([d["texto"] for d in docs], [d["tipo"] for d in docs])
    joblib.dump(modelo, args.modelo)
    print(f"modelo salvo em {args.modelo}")
    relatorio("VALIDAÇÃO CRUZADA NO TREINO (GroupKFold por lote), não é métrica final",
              linhas_de(docs, validacao_cruzada(docs)))
    return 0


def cmd_avaliar(args) -> int:
    import joblib
    modelo = joblib.load(args.modelo)
    docs = carregar(args.api, args.csv, _mapa(args.lote))
    print("baseline TF-IDF + regressão logística, sobre o documento do gabarito (segmentação não entra)")
    r = relatorio("BASELINE TF-IDF", linhas_de(docs, list(modelo.predict([d["texto"] for d in docs]))))
    if args.saida_json:
        saida = {"n": r["n"], "acuracia": r["acuracia"], "f1_macro": r["f1_macro"], "por_classe": r["por_classe"],
                 "matriz": {k: dict(v) for k, v in r["matriz"].items()}}
        Path(args.saida_json).write_text(json.dumps(saida, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for nome, fn in (("treinar", cmd_treinar), ("avaliar", cmd_avaliar)):
        p = sub.add_parser(nome)
        p.add_argument("csv")
        p.add_argument("--api", default="http://localhost:8000")
        p.add_argument("--modelo", default="modelo_baseline.joblib")
        p.add_argument("--lote", action="append", default=[], help="ID_CSV:ID_API (repetir)")
        if nome == "avaliar":
            p.add_argument("--saida-json")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
