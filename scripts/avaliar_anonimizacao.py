"""Mede a anonimização sobre lotes processados pela API, contra o gabarito documentos.jsonl.

Uso: python scripts/avaliar_anonimizacao.py documentos.jsonl [--api http://localhost:8000]
         [--lotes-dir DIR] [--lote L0001:1 ...]
- Sem --lotes-dir, os lotes já devem estar processados na API; o id do lote na API é o número de L000N
  (ou o mapa dado em --lote). Com --lotes-dir, envia DIR/L000N.pdf, espera concluir e mapeia sozinho.
- O texto vem do OCR guardado no banco (pagina.texto); a anonimização é a de app.anonimizacao.anonimizar_texto.
  A API devolve o CPF já mascarado, então a contagem de CPFs só faz sentido lendo o texto cru do banco:
  use --db (usa DATABASE_URL e psycopg; rode dentro do container: docker compose exec api python scripts/...).

Métricas (por documento do gabarito que tem campos.funcionario; o texto é o das páginas do documento):
- nomes que ainda aparecem: nome completo do funcionário (sem acento e sem caixa) presente no texto anonimizado;
  também reporta quantos têm algum sobrenome/nome (palavra de 4+ letras) sobrando.
- CPFs válidos que sobram no texto anonimizado (todos os CPFs, não só os do funcionário do gabarito).
- termos de tipo documental apagados por engano: ocorrências de app.anonimizacao.TERMOS_DOCUMENTAIS
  no texto original que não existem mais no anonimizado.
Nome errado por causa do OCR ruim aparece como 'nome não localizado no OCR' e fica fora do denominador.
"""
import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import anonimizacao  # noqa: E402
from scripts.api_http import abrir  # noqa: E402


def _norm(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


def _get(api: str, caminho: str):
    with abrir(api + caminho, timeout=60) as r:
        return json.load(r)


def _enviar(api: str, pdf: Path) -> int:
    limite = uuid.uuid4().hex
    corpo = (f"--{limite}\r\nContent-Disposition: form-data; name=\"arquivo\"; filename=\"{pdf.name}\"\r\n"
             "Content-Type: application/pdf\r\n\r\n").encode() + pdf.read_bytes() + f"\r\n--{limite}--\r\n".encode()
    req = urllib.request.Request(api + "/lotes", data=corpo, headers={
        "Content-Type": f"multipart/form-data; boundary={limite}"})
    with abrir(req, timeout=120) as r:
        return json.load(r)["lote_id"]


def _esperar(api: str, lote_id: int, espera: int = 900) -> None:
    fim = time.time() + espera
    while time.time() < fim:
        if _get(api, f"/lotes/{lote_id}")["estado"] in ("concluido", "erro"):
            return
        time.sleep(3)
    raise SystemExit(f"lote {lote_id} não concluiu em {espera}s")


def paginas_do_lote(api: str, lote_id: int, db: bool = False) -> dict[int, str]:
    """número da página no lote -> texto do OCR (independe de a segmentação ter acertado)."""
    if db:
        import os

        import psycopg
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            return {n: t or "" for n, t in conn.execute("SELECT numero, texto FROM pagina WHERE lote_id = %s", (lote_id,))}
    textos = {}
    for d in _get(api, f"/lotes/{lote_id}")["documentos"]:
        for p in _get(api, f"/documentos/{d['id']}")["paginas"]:
            textos[p["numero"]] = p["texto"] or ""
    return textos


def cpfs_validos(texto: str) -> list[str]:
    """CPFs válidos no texto, com ou sem pontuação e com espaços de OCR."""
    achados = []
    for m in re.finditer(r"(?<![\d.,/\-])\d{3}[ .]?\d{3}[ .]?\d{3}[ \-–]?\d{2}(?!\d)", texto):
        d = re.sub(r"\D", "", m.group(0))
        if anonimizacao._cpf_valido(d):
            achados.append(d)
    return achados


def avaliar_documento(texto: str, funcionario: str | None) -> dict:
    anon = anonimizacao.anonimizar_texto(texto) or ""
    n_anon, n_orig = _norm(anon), _norm(texto)
    res = {"cpfs_sobrando": len(cpfs_validos(anon)), "cpfs_originais": len(cpfs_validos(texto)),
           "termos_perdidos": {}, "nome_no_ocr": None, "nome_sobrou": None, "token_sobrou": None}
    for termo in anonimizacao.TERMOS_DOCUMENTAIS:
        t = _norm(termo)
        perdidos = n_orig.count(t) - n_anon.count(t)
        if perdidos > 0:
            res["termos_perdidos"][termo] = perdidos
    if funcionario:
        nome = _norm(funcionario)
        res["nome_no_ocr"] = nome in n_orig
        if res["nome_no_ocr"]:
            res["nome_sobrou"] = nome in n_anon
            tokens = [t for t in nome.split() if len(t) >= 4]
            res["token_sobrou"] = any(re.search(rf"\b{re.escape(t)}\b", n_anon) for t in tokens)
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("gabarito")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--lotes-dir")
    ap.add_argument("--lote", action="append", default=[], help="L0001:ID_NA_API")
    ap.add_argument("--detalhes", action="store_true")
    ap.add_argument("--db", action="store_true", help="lê o texto cru de pagina.texto (DATABASE_URL), não da API")
    a = ap.parse_args()
    mapa = dict(x.split(":") for x in a.lote)
    docs = [json.loads(l) for l in Path(a.gabarito).read_text(encoding="utf-8").splitlines() if l.strip()]
    lotes = sorted({d["lote_id"] for d in docs})
    ids = {}
    for lote in lotes:
        if a.lotes_dir:
            ids[lote] = _enviar(a.api, Path(a.lotes_dir) / f"{lote}.pdf")
            _esperar(a.api, ids[lote])
        else:
            ids[lote] = int(mapa.get(lote) or int(lote[1:]))
    paginas = {lote: paginas_do_lote(a.api, i, a.db) for lote, i in ids.items()}

    total = {"docs": 0, "com_nome": 0, "nome_no_ocr": 0, "nome_sobrou": 0, "token_sobrou": 0,
             "cpfs_originais": 0, "cpfs_sobrando": 0}
    perdidos: dict[str, int] = {}
    for d in docs:
        texto = "\n".join(paginas[d["lote_id"]].get(p, "") for p in range(d["pagina_inicial"], d["pagina_final"] + 1))
        func = d["campos"].get("funcionario")
        r = avaliar_documento(texto, func)
        total["docs"] += 1
        total["cpfs_originais"] += r["cpfs_originais"]
        total["cpfs_sobrando"] += r["cpfs_sobrando"]
        for t, n in r["termos_perdidos"].items():
            perdidos[t] = perdidos.get(t, 0) + n
        if func:
            total["com_nome"] += 1
            total["nome_no_ocr"] += bool(r["nome_no_ocr"])
            total["nome_sobrou"] += bool(r["nome_sobrou"])
            total["token_sobrou"] += bool(r["token_sobrou"])
            if a.detalhes and (r["nome_sobrou"] or r["token_sobrou"]):
                print(f"  sobrou: {d['documento_id']} {d['tipo']} nome={func!r} completo={r['nome_sobrou']}")
        if a.detalhes and r["termos_perdidos"]:
            print(f"  termos apagados em {d['documento_id']}: {r['termos_perdidos']}")

    ok = total["nome_no_ocr"]
    print(f"documentos avaliados: {total['docs']} (com nome de funcionário no gabarito: {total['com_nome']})")
    print(f"nome não localizado no OCR (fora do denominador): {total['com_nome'] - ok}")
    if ok:
        print(f"nome completo ainda aparece: {total['nome_sobrou']}/{ok} ({100 * total['nome_sobrou'] / ok:.1f}%)")
        print(f"algum nome/sobrenome (4+ letras) ainda aparece: {total['token_sobrou']}/{ok} "
              f"({100 * total['token_sobrou'] / ok:.1f}%)")
    print(f"CPFs válidos no texto original: {total['cpfs_originais']}; sobrando após anonimizar: {total['cpfs_sobrando']}")
    print(f"termos de tipo documental apagados por engano: {sum(perdidos.values())} {perdidos or ''}")
    print("dados sintéticos: vale só para o conjunto informado nos argumentos")


if __name__ == "__main__":
    main()
