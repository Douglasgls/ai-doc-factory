from fastapi import HTTPException, UploadFile
from pdf2image import pdfinfo_from_bytes

from app import config

from app.imagem import ArquivoInvalido, imagem_para_pdf


def converter_para_pdf(dados: bytes) -> bytes:
    """PDF passa direto; imagem é convertida. Arquivo inválido vira 400 (antes de tocar no banco)."""
    if dados.startswith(b"%PDF"):
        return dados
    try:
        return imagem_para_pdf(dados)
    except ArquivoInvalido as e:
        raise HTTPException(400, str(e))


_BLOCO = 1024 * 1024


def ler_com_limite(arquivo: UploadFile) -> bytes:
    """Lê o upload em blocos de 1 MB e para ao passar de `UPLOAD_MAX_MB` (413), sem carregar o arquivo inteiro."""
    limite = config.UPLOAD_MAX_MB * _BLOCO
    partes, total = [], 0
    while bloco := arquivo.file.read(_BLOCO):
        total += len(bloco)
        if total > limite:
            raise HTTPException(413, f"arquivo maior que {config.UPLOAD_MAX_MB:g} MB")
        partes.append(bloco)
    return b"".join(partes)


def validar_paginas(pdf: bytes) -> None:
    """Acima de `UPLOAD_MAX_PAGINAS` páginas: 422. Se o poppler não consegue ler o PDF, não decide aqui
    (o comportamento de hoje, o OCR trata o arquivo)."""
    try:
        paginas = int(pdfinfo_from_bytes(pdf)["Pages"])
    except Exception:
        return
    if paginas > config.UPLOAD_MAX_PAGINAS:
        raise HTTPException(422, f"o lote tem {paginas} páginas; o máximo é {config.UPLOAD_MAX_PAGINAS}")
