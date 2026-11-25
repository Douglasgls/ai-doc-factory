"""Handler de segmentar_lote: extrai texto nativo via PyMuPDF quando disponível ou rasteriza e roda Tesseract."""
import logging
import os
import re
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import redis
from pdf2image import convert_from_path, pdfinfo_from_path

try:
    import fitz  # PyMuPDF
except ImportError:  # pragma: no cover
    fitz = None

from app import config
from app.eventos import limpar_tarefas_pos, lote_cancelado, publicar_evento, registrar_tarefas_pos
from app.filas import enfileirar
from app.segmentacao import segmentar

log = logging.getLogger(__name__)
DPI = 150
PARALELISMO = 4
# Uma thread OpenMP por processo do Tesseract: o paralelismo fica no pool acima (e nas réplicas do worker).
# Sem isso cada tesseract abre uma thread por núcleo e réplicas x pool x núcleos disputam a CPU.
_ENV_TESSERACT = {**os.environ, "OMP_THREAD_LIMIT": "1"}
# PyMuPDF (fitz) não é thread-safe segundo a documentação oficial: toda leitura/rasterização com fitz
# roda serializada numa única thread; apenas o subprocesso do Tesseract roda em paralelo no ThreadPoolExecutor.
_FITZ_LOCK = threading.Lock()

MIN_PALAVRAS_NATIVAS = 5
MIN_CHARS_NATIVOS = 40
LIMIAR_AREA_IMAGEM_SCAN = 0.65
_RE_PALAVRA_LIMPA = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def _pagina_coberta_por_imagem_scan(page) -> bool:
    """True se a página possui uma imagem raster cobrindo >= 65% da sua área (documento escaneado/foto)."""
    rect = page.rect
    area_pag = abs(rect.width * rect.height)
    if area_pag <= 0:
        return False
    try:
        imagens = page.get_image_info() or []
    except Exception:
        return False
    for img in imagens:
        bbox = img.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        x0 = max(rect.x0, float(bbox[0]))
        y0 = max(rect.y0, float(bbox[1]))
        x1 = min(rect.x1, float(bbox[2]))
        y1 = min(rect.y1, float(bbox[3]))
        area_img = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        if area_img / area_pag >= LIMIAR_AREA_IMAGEM_SCAN:
            return True
    return False


def extrair_texto_nativo_pagina(page) -> str | None:
    """Extrai o texto digital nativo de uma página PyMuPDF ordenado por blocos visuais.
    Devolve None se a página for um scan/foto, estiver em branco ou tiver codificação corrompida."""
    if _pagina_coberta_por_imagem_scan(page):
        return None
    try:
        blocos = page.get_text("blocks") or []
    except Exception:
        return None
    blocos_texto = [
        (round(float(b[1]), 1), round(float(b[0]), 1), str(b[4]).replace("\x00", "").strip())
        for b in blocos
        if len(b) >= 7 and b[6] == 0 and str(b[4]).replace("\x00", "").strip()
    ]
    if not blocos_texto:
        return None
    blocos_texto.sort(key=lambda item: (item[0], item[1]))
    texto = "\n".join(item[2] for item in blocos_texto).strip()
    if "\ufffd" in texto:
        return None
    sem_espaco = re.sub(r"\s+", "", texto)
    if len(sem_espaco) < MIN_CHARS_NATIVOS:
        return None
    if len(_RE_PALAVRA_LIMPA.findall(texto)) < MIN_PALAVRAS_NATIVAS:
        return None
    return texto


def ocr_imagem(png: Path) -> str:
    """Tesseract em português. Página em branco devolve texto vazio."""
    saida = subprocess.run(
        ["tesseract", str(png), "stdout", "-l", "por"],
        check=True, capture_output=True, text=True, encoding="utf-8", env=_ENV_TESSERACT,
    ).stdout
    return saida.replace("\x00", "").strip()  # Postgres não aceita NUL em TEXT


def _limpar_cache_fitz() -> None:
    """Libera o cache interno de imagens do MuPDF (padrão ~256 MB) para conter o pico de RAM nos workers."""
    if fitz is not None:
        try:
            fitz.TOOLS.store_shrink(100)
        except Exception:
            pass


def processar_pagina(pdf: Path, pasta: Path, numero: int) -> tuple[int, str, bool]:
    """Gera o PNG da página (150 DPI) para visualização/fallback e devolve (numero, texto, texto_nativo).
    Se a página for um PDF digital nativo válido, extrai o texto via PyMuPDF sem rodar o Tesseract."""
    png = pasta / f"pag_{numero:04d}.png"
    if fitz is not None:
        with _FITZ_LOCK:
            try:
                with fitz.open(str(pdf)) as doc:
                    page = doc[numero - 1]
                    pix = page.get_pixmap(dpi=DPI, alpha=False)
                    pix.save(str(png))
                    del pix
                    texto_nativo = extrair_texto_nativo_pagina(page)
            finally:
                _limpar_cache_fitz()
        if texto_nativo is not None:
            log.info("%s | página %04d -> texto nativo (PyMuPDF, %d chars; Tesseract pulado)",
                     pasta.name, numero, len(texto_nativo))
            return numero, texto_nativo, True
        texto_ocr = ocr_imagem(png)
        log.info("%s | página %04d -> escaneada/imagem (Tesseract OCR, %d chars)",
                 pasta.name, numero, len(texto_ocr))
        return numero, texto_ocr, False
    imagem = convert_from_path(str(pdf), dpi=DPI, first_page=numero, last_page=numero)[0]
    imagem.save(png)
    texto_ocr = ocr_imagem(png)
    log.info("%s | página %04d -> fallback Poppler + Tesseract OCR (%d chars)",
             pasta.name, numero, len(texto_ocr))
    return numero, texto_ocr, False


def _processar_paginas_lote(pdf: Path, pasta: Path, total: int) -> list[tuple[int, str, bool]]:
    """Extrai páginas nativas e gera PNGs em sequência numa única thread (PyMuPDF não é thread-safe),
    deixando apenas o Tesseract OCR das páginas escaneadas rodando em paralelo no ThreadPoolExecutor."""
    if fitz is None:
        with ThreadPoolExecutor(PARALELISMO) as pool:
            return list(pool.map(lambda n: processar_pagina(pdf, pasta, n), range(1, total + 1)))

    resultados: dict[int, tuple[int, str, bool]] = {}
    pendentes_ocr: list[tuple[int, Path]] = []

    with _FITZ_LOCK:
        try:
            with fitz.open(str(pdf)) as doc:
                for numero in range(1, total + 1):
                    png = pasta / f"pag_{numero:04d}.png"
                    page = doc[numero - 1]
                    pix = page.get_pixmap(dpi=DPI, alpha=False)
                    pix.save(str(png))
                    del pix
                    texto_nativo = extrair_texto_nativo_pagina(page)
                    if texto_nativo is not None:
                        log.info("%s | página %04d -> texto nativo (PyMuPDF, %d chars; Tesseract pulado)",
                                 pasta.name, numero, len(texto_nativo))
                        resultados[numero] = (numero, texto_nativo, True)
                    else:
                        pendentes_ocr.append((numero, png))
                    _limpar_cache_fitz()
        finally:
            _limpar_cache_fitz()

    if pendentes_ocr:
        def _rodar_ocr(item: tuple[int, Path]) -> tuple[int, str, bool]:
            numero, png = item
            texto_ocr = ocr_imagem(png)
            log.info("%s | página %04d -> escaneada/imagem (Tesseract OCR, %d chars)",
                     pasta.name, numero, len(texto_ocr))
            return numero, texto_ocr, False

        with ThreadPoolExecutor(PARALELISMO) as pool:
            for res in pool.map(_rodar_ocr, pendentes_ocr):
                resultados[res[0]] = res

    return [resultados[n] for n in range(1, total + 1)]


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
        if conn.execute("SELECT 1 FROM documento WHERE lote_id = %s AND estado = 'revisado' LIMIT 1",
                        (lote_id,)).fetchone():
            # defesa: regravar apagaria a revisão humana. Sem erro (não vai à dlq em loop); o lote fica em 'erro',
            # o mesmo estado de um lote cancelado, em vez de preso em 'ocr'.
            log.warning("lote %s possui documentos revisados: segmentação não regravada", lote_id)
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


def marcar_erro_lote(payload: dict) -> None:
    """ao_esgotar: o job foi para a dlq. Marca o lote como 'erro' (só se ainda estiver em 'ocr') e avisa."""
    lote_id = payload["lote_id"]
    with psycopg.connect(config.DATABASE_URL) as conn:
        row = conn.execute("UPDATE lote SET estado = 'erro' WHERE id = %s AND estado = 'ocr' RETURNING id",
                           (lote_id,)).fetchone()
    if row is not None:
        publicar_evento(lote_id, "erro", "Falha no processamento de OCR/segmentação.")


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
    with psycopg.connect(config.DATABASE_URL) as conn:
        tem_revisao = conn.execute("SELECT 1 FROM documento WHERE lote_id = %s AND estado = 'revisado' LIMIT 1",
                                   (lote_id,)).fetchone()
        if tem_revisao:  # job antigo: não refaz OCR/LLM nem apaga a revisão humana; sem exceção (não vai à dlq)
            log.warning("lote %s possui documentos revisados: processamento ignorado", lote_id)
            conn.execute("UPDATE lote SET estado = 'erro', docs_pendentes = 0 WHERE id = %s", (lote_id,))
    if tem_revisao:
        publicar_evento(lote_id, "erro", "Lote possui revisão humana e não foi reprocessado.")
        return
    pasta = Path(config.DATA_DIR) / f"lote_{lote_id}"
    pdf = pasta / "original.pdf"
    _estado(lote_id, "ocr")
    publicar_evento(lote_id, "ocr", "Iniciando conversão e leitura OCR das páginas...")
    try:
        total = pdfinfo_from_path(str(pdf))["Pages"]
        publicar_evento(lote_id, "ocr", f"Lendo OCR de {total} página(s)...", pagina_atual=0, total_paginas=total)
        resultados = _processar_paginas_lote(pdf, pasta, total)
        if lote_cancelado(lote_id):
            _marcar_lote_cancelado_db(lote_id)
            limpar_tarefas_pos(lote_id)
            publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.")
            return
        with psycopg.connect(config.DATABASE_URL) as conn:
            for item in resultados:
                numero, texto = item[0], item[1]
                nativo = bool(item[2]) if len(item) > 2 else False
                conn.execute(
                    "INSERT INTO pagina (lote_id, numero, texto, texto_nativo) VALUES (%s, %s, %s, %s) "
                    "ON CONFLICT (lote_id, numero) DO UPDATE SET texto = EXCLUDED.texto, "
                    "texto_nativo = EXCLUDED.texto_nativo",
                    (lote_id, numero, texto, nativo),
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
        # 'erro' só ao esgotar as tentativas (marcar_erro_lote, via ao_esgotar); entre elas o lote segue em 'ocr'
        publicar_evento(lote_id, "ocr", "Falha temporária no OCR/segmentação; tentando de novo em instantes.")
        raise
    if lote_cancelado(lote_id):
        _marcar_lote_cancelado_db(lote_id)
        limpar_tarefas_pos(lote_id)
        publicar_evento(lote_id, "cancelado", "Processamento cancelado pelo usuário.")
        return
    if not ids:
        return
    log.info("lote %s: leitura de %s páginas e segmentação em %s documentos", lote_id, total, len(ids))
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
