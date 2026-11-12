"""Handler de segmentar_lote: rasteriza o PDF, roda Tesseract por página e grava o texto."""
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import redis
from pdf2image import convert_from_path, pdfinfo_from_path

from app import config
from app.eventos import limpar_tarefas_pos, lote_cancelado, publicar_evento, registrar_tarefas_pos
from app.filas import enfileirar
from app.segmentacao import segmentar

log = logging.getLogger(__name__)
DPI = 150
PARALELISMO = 4


def ocr_imagem(png: Path) -> str:
    """Tesseract em português. Página em branco devolve texto vazio."""
    saida = subprocess.run(
        ["tesseract", str(png), "stdout", "-l", "por"],
        check=True, capture_output=True, text=True, encoding="utf-8",
    ).stdout
    return saida.replace("\x00", "").strip()  # Postgres não aceita NUL em TEXT


def processar_pagina(pdf: Path, pasta: Path, numero: int) -> tuple[int, str]:
    png = pasta / f"pag_{numero:04d}.png"
    imagem = convert_from_path(str(pdf), dpi=DPI, first_page=numero, last_page=numero)[0]
    imagem.save(png)
    return numero, ocr_imagem(png)


def _estado(lote_id: int, estado: str) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute("UPDATE lote SET estado = %s WHERE id = %s", (estado, lote_id))


def _marcar_lote_cancelado_db(lote_id: int) -> None:
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute(
            "UPDATE documento SET estado = 'erro' WHERE lote_id = %s AND estado = 'segmentado'",
            (lote_id,),
        )
        conn.execute(
            "UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s AND estado != 'concluido'",
            (lote_id,),
        )


def _reenfileirar_pendentes(lote_id: int) -> None:
    """Lote já em 'classificando': cobre a queda entre o commit da segmentação e o enfileiramento."""
    with psycopg.connect(config.DATABASE_URL) as conn:
        ids = [r[0] for r in conn.execute(
            "SELECT id FROM documento WHERE lote_id = %s AND estado = 'segmentado' ORDER BY ordem", (lote_id,))]
    _enfileirar_classificacao(ids)


def _enfileirar_classificacao(ids: list[int]) -> None:
    r = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    for id_ in ids:
        enfileirar(r, config.FILA_CLASSIFICAR, {"documento_id": id_})


def segmentar_e_gravar(lote_id: int) -> list[int]:
    """Recria os documentos do lote, vincula as páginas, define docs_pendentes e muda o lote para
    'classificando', em uma única transação. Devolve os ids dos documentos (vazio se outro worker já fez).

    A segmentação (que pode chamar o LLM, ou seja, rede) roda ANTES da transação: o FOR UPDATE não pode
    ficar preso durante chamada de rede. O estado é conferido de novo sob o lock."""
    if lote_cancelado(lote_id):
        _marcar_lote_cancelado_db(lote_id)
        return []
    with psycopg.connect(config.DATABASE_URL) as conn:
        estado = conn.execute("SELECT estado FROM lote WHERE id = %s", (lote_id,)).fetchone()[0]
        if estado in ("classificando", "concluido"):
            return []
        textos = [t or "" for (t,) in conn.execute(
            "SELECT texto FROM pagina WHERE lote_id = %s ORDER BY numero", (lote_id,))]
    docs = segmentar(textos)
    with psycopg.connect(config.DATABASE_URL) as conn:  # o with faz commit único ao sair
        estado = conn.execute("SELECT estado FROM lote WHERE id = %s FOR UPDATE", (lote_id,)).fetchone()[0]
        if estado in ("classificando", "concluido"):
            return []
        if lote_cancelado(lote_id):
            conn.execute("UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s", (lote_id,))
            return []
        conn.execute("DELETE FROM documento WHERE lote_id = %s", (lote_id,))  # refazer não duplica
        ids = []
        for ordem, d in enumerate(docs, start=1):
            id_ = conn.execute(
                "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, segmentacao_ambigua) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (lote_id, ordem, d.pagina_ini, d.pagina_fim, d.ambiguo),
            ).fetchone()[0]
            conn.execute(
                "UPDATE pagina SET documento_id = %s WHERE lote_id = %s AND numero BETWEEN %s AND %s",
                (id_, lote_id, d.pagina_ini, d.pagina_fim),
            )
            ids.append(id_)
        conn.execute("UPDATE lote SET docs_pendentes = %s, estado = 'classificando' WHERE id = %s",
                     (len(ids), lote_id))
    return ids


def processar_lote(payload: dict) -> None:
    lote_id = payload["lote_id"]
    if lote_cancelado(lote_id):
        _marcar_lote_cancelado_db(lote_id)
        limpar_tarefas_pos(lote_id)
        publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.")
        return
    with psycopg.connect(config.DATABASE_URL) as conn:
        estado = conn.execute("SELECT estado FROM lote WHERE id = %s", (lote_id,)).fetchone()[0]
    if estado == "concluido":
        return
    if estado == "classificando":
        _reenfileirar_pendentes(lote_id)
        return
    pasta = Path(config.DATA_DIR) / f"lote_{lote_id}"
    pdf = pasta / "original.pdf"
    _estado(lote_id, "ocr")
    publicar_evento(lote_id, "ocr", "Iniciando conversão e leitura OCR das páginas...")
    try:
        total = pdfinfo_from_path(str(pdf))["Pages"]
        publicar_evento(lote_id, "ocr", f"Lendo OCR de {total} página(s)...", pagina_atual=0, total_paginas=total)
        with ThreadPoolExecutor(PARALELISMO) as pool:
            resultados = list(pool.map(lambda n: processar_pagina(pdf, pasta, n), range(1, total + 1)))
        if lote_cancelado(lote_id):
            _marcar_lote_cancelado_db(lote_id)
            limpar_tarefas_pos(lote_id)
            publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.")
            return
        with psycopg.connect(config.DATABASE_URL) as conn:
            for numero, texto in resultados:
                conn.execute(
                    "INSERT INTO pagina (lote_id, numero, texto) VALUES (%s, %s, %s) "
                    "ON CONFLICT (lote_id, numero) DO UPDATE SET texto = EXCLUDED.texto",
                    (lote_id, numero, texto),
                )
        publicar_evento(
            lote_id,
            "segmentacao",
            f"OCR de {total} página(s) concluído · segmentando documentos...",
            pagina_atual=total,
            total_paginas=total,
        )
        ids = segmentar_e_gravar(lote_id)
    except Exception:
        _estado(lote_id, "erro")  # o retry da fila volta o lote para 'ocr'
        publicar_evento(lote_id, "erro", "Falha no processamento de OCR/segmentação.")
        raise
    if lote_cancelado(lote_id):
        _marcar_lote_cancelado_db(lote_id)
        limpar_tarefas_pos(lote_id)
        publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.")
        return
    if not ids:
        return
    log.info("lote %s: OCR de %s páginas e segmentação em %s documentos", lote_id, total, len(ids))
    registrar_tarefas_pos(lote_id, [f"extracao:{id_}" for id_ in ids])
    publicar_evento(
        lote_id,
        "classificando",
        f"{len(ids)} documento(s) identificado(s) · iniciando classificação por IA...",
        total_paginas=total,
        total_documentos=len(ids),
        docs_pendentes=len(ids),
    )
    _enfileirar_classificacao(ids)  # se cair antes daqui, o retry vê 'classificando' e reenfileira
