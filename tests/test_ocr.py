"""Rodar no compose: docker compose exec api python -m pytest tests (precisa de Tesseract, só existe na imagem)."""
from PIL import Image, ImageDraw, ImageFont

from app.ocr import ocr_imagem

FONTE = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def test_pagina_em_branco_devolve_texto_vazio(tmp_path):
    png = tmp_path / "branco.png"
    Image.new("RGB", (1240, 1754), "white").save(png)
    assert ocr_imagem(png) == ""


def test_ocr_portugues_com_acento(tmp_path):
    png = tmp_path / "texto.png"
    im = Image.new("RGB", (1240, 400), "white")
    ImageDraw.Draw(im).text((50, 50), "Funcionário: Zeferino Tavares", fill="black", font=ImageFont.truetype(FONTE, 30))
    im.save(png)
    assert "Funcionário: Zeferino" in ocr_imagem(png)


def test_tesseract_roda_com_uma_thread_openmp(monkeypatch, tmp_path):
    """O paralelismo é do pool e das réplicas; cada tesseract não pode abrir uma thread por núcleo."""
    import subprocess

    from app import ocr

    chamadas = []

    def falso_run(cmd, **kw):
        chamadas.append(kw.get("env") or {})
        return subprocess.CompletedProcess(cmd, 0, stdout="texto\x00", stderr="")

    monkeypatch.setattr(ocr.subprocess, "run", falso_run)
    assert ocr.ocr_imagem(tmp_path / "x.png") == "texto"
    assert chamadas[0].get("OMP_THREAD_LIMIT") == "1"
    assert "PATH" in chamadas[0]  # herda o ambiente
