"""Testes da leitura híbrida por página com PyMuPDF (PDF digital vs. escaneado)
e da extração de campos em cascata (só texto com fallback automático para imagem PNG)."""
import io
import json
import uuid

import fitz
import psycopg
import pytest
from PIL import Image

from app import config, extracao, llm, ocr
from app.imagem import imagem_para_pdf


def _criar_pdf_digital(caminho, linhas: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    y = 72
    for linha in linhas:
        page.insert_text((50, y), linha, fontsize=12)
        y += 22
    doc.save(str(caminho))
    doc.close()


def test_pdf_digital_extrai_texto_via_pymupdf_sem_chamar_tesseract(tmp_path, monkeypatch):
    pdf = tmp_path / "original.pdf"
    _criar_pdf_digital(
        pdf,
        [
            "ATESTADO DE SAUDE OCUPACIONAL - ASO",
            "Empregador: Servicos Horizonte Ltda - CNPJ: 11.222.333/0001-81",
            "Funcionario: Maria Aparecida Souza - CPF: 529.982.247-25",
            "Tipo de exame: Periodico - Data do exame: 15/03/2025 - Parecer: APTO",
        ],
    )
    monkeypatch.setattr(ocr, "ocr_imagem", lambda *_: pytest.fail("não deve rodar Tesseract em PDF digital nativo"))

    numero, texto, texto_nativo = ocr.processar_pagina(pdf, tmp_path, 1)

    assert numero == 1
    assert texto_nativo is True
    assert "Servicos Horizonte Ltda" in texto
    assert "529.982.247-25" in texto
    assert (tmp_path / "pag_0001.png").is_file()


def test_pdf_escaneado_de_imagem_aciona_tesseract_e_marca_falso(tmp_path, monkeypatch):
    buf = io.BytesIO()
    Image.new("RGB", (1240, 1754), "white").save(buf, format="PNG")
    pdf_bytes = imagem_para_pdf(buf.getvalue())
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(pdf_bytes)

    chamou_tesseract = []

    def falso_ocr(png):
        chamou_tesseract.append(png)
        return "Texto lido pelo Tesseract no scan"

    monkeypatch.setattr(ocr, "ocr_imagem", falso_ocr)

    numero, texto, texto_nativo = ocr.processar_pagina(pdf, tmp_path, 1)

    assert numero == 1
    assert texto_nativo is False
    assert texto == "Texto lido pelo Tesseract no scan"
    assert len(chamou_tesseract) == 1


def test_pagina_com_caractere_corrompido_ou_curta_cai_para_tesseract(tmp_path, monkeypatch):
    pdf = tmp_path / "curto.pdf"
    _criar_pdf_digital(pdf, ["Oi"])
    monkeypatch.setattr(ocr, "ocr_imagem", lambda *_: "ocr fallback")

    _, texto, texto_nativo = ocr.processar_pagina(pdf, tmp_path, 1)
    assert texto_nativo is False
    assert texto == "ocr fallback"


@pytest.mark.parametrize("tipo,campos,esperado", [
    ("aso", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "data_exame": "2025-03-15", "tipo_exame": "periodico",
    }, True),
    ("aso", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "data_exame": "2025-03-15",  # faltou tipo_exame (ex.: marcado a caneta)
    }, False),
    ("aso", {
        "cnpj_prestadora": "11.222.333/0001-00", "nome": "Maria", "cpf": "529.982.247-25",
        "data_exame": "2025-03-15", "tipo_exame": "periodico",  # CNPJ com dígito inválido
    }, False),
    ("contrato_trabalho", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "data_admissao": "2025-01-10", "tipo_prazo": "indeterminado",
    }, True),
    ("contrato_trabalho", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "data_admissao": "2025-01-10", "tipo_prazo": "determinado",  # faltou data_termino
    }, False),
    ("contrato_trabalho", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "data_admissao": "2025-01-10", "tipo_prazo": "determinado", "data_termino": "2025-04-10",
    }, True),
    ("holerite", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "competencia": "2025-03",
    }, True),
    ("folha_pagamento", {
        "cnpj_prestadora": "11.222.333/0001-81", "competencia": "2025-03",
    }, True),
    ("folha_ponto", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "competencia": "2025-03",
    }, True),
    ("recibo_ferias", {
        "cnpj_prestadora": "11.222.333/0001-81", "nome": "Maria", "cpf": "529.982.247-25",
        "inicio_ferias": "2025-03-01", "fim_ferias": "2025-03-30",
    }, True),
    ("atestado_medico", {"nome": "Maria", "data_emissao": "2025-03-10"}, True),
    ("atestado_medico", {"nome": "Maria"}, False),
])
def test_campos_essenciais_completos_por_tipo(tipo, campos, esperado):
    assert extracao.campos_essenciais_completos(tipo, campos) is esperado


@pytest.fixture
def criar_doc_extracao(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", str(tmp_path))
    lotes_criados = []

    def _criar(tipo: str, texto_nativo: bool, com_png: bool = True) -> int:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            lote_id = conn.execute(
                "INSERT INTO lote (sha256, nome_arquivo, estado, docs_pendentes) "
                "VALUES (%s, 'lote.pdf', 'concluido', 0) RETURNING id",
                (uuid.uuid4().hex + uuid.uuid4().hex,),
            ).fetchone()[0]
            lotes_criados.append(lote_id)
            doc_id = conn.execute(
                "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo) "
                "VALUES (%s, 1, 1, 1, 'classificado', %s) RETURNING id",
                (lote_id, tipo),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO pagina (lote_id, numero, documento_id, texto, texto_nativo) "
                "VALUES (%s, 1, %s, 'Texto da pagina 1', %s)",
                (lote_id, doc_id, texto_nativo),
            )
        if com_png:
            pasta = tmp_path / f"lote_{lote_id}"
            pasta.mkdir(parents=True, exist_ok=True)
            (pasta / "pag_0001.png").write_bytes(b"PNG_BYTES_FICTICIOS")
        return doc_id

    yield _criar

    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        for lid in lotes_criados:
            conn.execute("DELETE FROM lote WHERE id = %s", (lid,))


def _campos_banco(doc_id: int) -> dict[str, str]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        rows = conn.execute("SELECT campo, valor FROM documento_campos WHERE documento_id = %s", (doc_id,)).fetchall()
    return dict(rows)


def test_extracao_pagina_nativa_completa_nao_envia_imagem_ao_gemini(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("holerite", texto_nativo=True)
    imagens_enviadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        imagens_enviadas.append(imagem_png)
        resposta = {
            "cnpj_prestadora": "11.222.333/0001-81",
            "razao_social_prestadora": "Alfa Ltda",
            "nome": "Maria Silva",
            "cpf": "529.982.247-25",
            "competencia": "2025-03",
        }
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(resposta)}]}}]}

    monkeypatch.setattr(llm, "gemini_gerar", falso_gemini)
    extracao.extrair_campos({"documento_id": doc_id})

    assert imagens_enviadas == [None]  # 1 única chamada e sem imagem PNG!
    campos = _campos_banco(doc_id)
    assert campos["cnpj_prestadora"] == "11.222.333/0001-81"
    assert campos["competencia"] == "2025-03"


def test_extracao_pagina_nativa_incompleta_faz_fallback_automatico_com_imagem(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("aso", texto_nativo=True)
    imagens_enviadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        imagens_enviadas.append(imagem_png)
        if imagem_png is None:
            # 1ª tentativa (só texto): faltou data_exame e tipo_exame (ex.: estavam em carimbo/checkbox na imagem)
            parcial = {
                "cnpj_prestadora": "11.222.333/0001-81",
                "nome": "Maria Silva",
                "cpf": "529.982.247-25",
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(parcial)}]}}]}
        # 2ª tentativa (fallback com imagem): Gemini Vision lê o carimbo e o checkbox
        completo = {
            "cnpj_prestadora": "11.222.333/0001-81",
            "nome": "Maria Silva",
            "cpf": "529.982.247-25",
            "data_exame": "15/03/2025",
            "tipo_exame": "periodico",
        }
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(completo)}]}}]}

    monkeypatch.setattr(llm, "gemini_gerar", falso_gemini)
    extracao.extrair_campos({"documento_id": doc_id})

    assert imagens_enviadas == [None, b"PNG_BYTES_FICTICIOS"]
    campos = _campos_banco(doc_id)
    assert campos["data_exame"] == "2025-03-15"
    assert campos["tipo_exame"] == "periodico"
    assert campos["nome"] == "Maria Silva"


def test_extracao_pagina_escaneada_envia_imagem_direto_na_primeira_chamada(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("aso", texto_nativo=False)
    imagens_enviadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        imagens_enviadas.append(imagem_png)
        completo = {
            "cnpj_prestadora": "11.222.333/0001-81",
            "nome": "Maria Silva",
            "cpf": "529.982.247-25",
            "data_exame": "15/03/2025",
            "tipo_exame": "periodico",
        }
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(completo)}]}}]}

    monkeypatch.setattr(llm, "gemini_gerar", falso_gemini)
    extracao.extrair_campos({"documento_id": doc_id})

    assert imagens_enviadas == [b"PNG_BYTES_FICTICIOS"]


def test_lote_misto_pagina_digital_e_pagina_escaneada(tmp_path, monkeypatch):
    """Em um mesmo PDF com página 1 digital e página 2 escaneada, só a página 2 roda Tesseract."""
    doc = fitz.open()
    # Página 1: PDF digital nativo
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "HOLERITE MENSAL - FOLHA DE PAGAMENTO INDIVIDUAL", fontsize=12)
    p1.insert_text((50, 96), "Empregador: Servicos Horizonte Ltda CNPJ 11.222.333/0001-81", fontsize=12)
    p1.insert_text((50, 120), "Empregado: Joao Carlos Pereira CPF 529.982.247-25 Competencia 03/2025", fontsize=12)

    # Página 2: Imagem escaneada cobrindo a página inteira
    p2 = doc.new_page(width=595, height=842)
    buf = io.BytesIO()
    Image.new("RGB", (600, 850), "white").save(buf, format="PNG")
    p2.insert_image(p2.rect, stream=buf.getvalue())

    pdf = tmp_path / "misto.pdf"
    doc.save(str(pdf))
    doc.close()

    paginas_tesseract = []

    def falso_ocr(png):
        paginas_tesseract.append(png.name)
        return "ATESTADO MEDICO escaneado"

    monkeypatch.setattr(ocr, "ocr_imagem", falso_ocr)

    _, t1, nat1 = ocr.processar_pagina(pdf, tmp_path, 1)
    _, t2, nat2 = ocr.processar_pagina(pdf, tmp_path, 2)

    assert nat1 is True and "Joao Carlos Pereira" in t1
    assert nat2 is False and t2 == "ATESTADO MEDICO escaneado"
    assert paginas_tesseract == ["pag_0002.png"]


