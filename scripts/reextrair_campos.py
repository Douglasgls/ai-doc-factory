"""Reenfileira a extração de campos (Goal 7) dos documentos com extração de versão antiga ou sem extração.

ATENÇÃO: cada documento enfileirado com --executar gasta uma chamada ao Gemini (ou duas, se um documento
com texto nativo precisar de fallback com imagem). Use --lote e --limite para controlar o custo. Sem
--executar só lista (dry-run) e não enfileira nada.

Uso: python scripts/reextrair_campos.py [--lote ID] [--limite N] [--executar]

Entra: documento em estado classificado, revisado ou em_revisao (os mesmos que o handler de extração aceita)
cuja extração gravada (documento_campos.origem = 'gemini:<versao>') seja de uma versão diferente de
VERSAO_PROMPT_EXTRACAO e VERSAO_PROMPT_EXTRACAO_TEXTO, ou que não tenha nenhuma extração do Gemini. Documento cuja extração anterior não
devolveu nenhum campo também conta como sem extração. O handler só substitui campos de origem gemini:*;
correção humana (origem 'humano') nunca é apagada. Usa a fila e o payload de sempre: {"documento_id": id}.
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # permite importar app/ ao rodar o script direto
from app import config, prompts  # noqa: E402

ESTADOS = ("classificado", "revisado", "em_revisao")
SEM_EXTRACAO = "(sem extração)"


def selecionar(
    conn, versao_atual: str | tuple[str, ...], lote: int | None = None, limite: int | None = None
) -> list[tuple[int, str]]:
    """[(documento_id, versao_gravada ou SEM_EXTRACAO)] dos documentos que precisam de nova extração, por id."""
    versoes = (versao_atual,) if isinstance(versao_atual, str) else tuple(versao_atual)
    atuais = {f"gemini:{v}" for v in versoes}
    linhas = conn.execute(
        "SELECT d.id, "
        "  (SELECT string_agg(DISTINCT c.origem, ',' ORDER BY c.origem) FROM documento_campos c "
        "   WHERE c.documento_id = d.id AND c.origem LIKE 'gemini:%%') AS origens "
        "FROM documento d WHERE d.estado = ANY(%s) AND (%s::int IS NULL OR d.lote_id = %s) "
        "ORDER BY d.id",
        (list(ESTADOS), lote, lote),
    ).fetchall()
    saida = []
    for doc_id, origens in linhas:
        if origens is None:
            saida.append((doc_id, SEM_EXTRACAO))
        elif origens not in atuais:
            saida.append((doc_id, ",".join(o.removeprefix("gemini:") for o in origens.split(","))))
    return saida[:limite] if limite else saida


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lote", type=int, help="só documentos deste lote")
    ap.add_argument("--limite", type=int, help="no máximo N documentos (controla o custo)")
    ap.add_argument("--executar", action="store_true",
                    help="enfileira de verdade (cada documento gasta uma chamada ao Gemini); sem isto é dry-run")
    args = ap.parse_args(argv)
    if args.limite is not None and args.limite <= 0:
        ap.error("--limite deve ser positivo")

    versoes_atuais = (prompts.VERSAO_PROMPT_EXTRACAO, prompts.VERSAO_PROMPT_EXTRACAO_TEXTO)
    with psycopg.connect(config.DATABASE_URL) as conn:
        docs = selecionar(conn, versoes_atuais, args.lote, args.limite)
    print(f"versões atuais do prompt: {', '.join(versoes_atuais)}")
    print(f"documentos a reextrair: {len(docs)}")
    for versao, n in sorted(Counter(v for _, v in docs).items()):
        print(f"  {versao}: {n}")
    if docs:
        print("ids:", ", ".join(str(i) for i, _ in docs))
    if not args.executar:
        print("dry-run: nada foi enfileirado (use --executar; cada documento gasta uma chamada ao Gemini)")
        return 0

    import redis

    from app.extracao import enfileirar_extracao
    cli = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    falhas = [i for i, _ in docs if enfileirar_extracao(i, cli) is False]  # só False é falha explícita
    print(f"enfileirados: {len(docs) - len(falhas)} de {len(docs)} na fila {config.FILA_EXTRAIR}")
    if falhas:
        print("falhou ao enfileirar:", ", ".join(map(str, falhas)))
    return 1 if falhas else 0


if __name__ == "__main__":
    sys.exit(main())
