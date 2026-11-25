"""Testes da leitura híbrida por página com PyMuPDF (PDF digital vs. escaneado)
e da extração de campos em cascata (só texto com fallback automático para imagem PNG)."""
import io
import json
import sys
import threading
import uuid
from pathlib import Path

import fitz
import psycopg
import pytest
from PIL import Image

from app import config, extracao, llm, ocr, prompts
from app.imagem import imagem_para_pdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts import reextrair_campos  # noqa: E402


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


def _origens_banco(doc_id: int) -> set[str]:
    with psycopg.connect(config.DATABASE_URL) as conn:
        rows = conn.execute("SELECT DISTINCT origem FROM documento_campos WHERE documento_id = %s", (doc_id,)).fetchall()
    return {r[0] for r in rows}


def test_prompt_extracao_sem_imagem_usa_instrucoes_dedicadas_e_versao_propria():
    assert prompts.VERSAO_PROMPT_EXTRACAO == "gemini-extracao-v4"
    assert prompts.VERSAO_PROMPT_EXTRACAO_TEXTO == "gemini-extracao-texto-v1"
    p_img = prompts.prompt_extracao("holerite", "texto exemplo", com_imagem=True)
    p_txt = prompts.prompt_extracao("holerite", "texto exemplo", com_imagem=False)
    assert "Use a imagem da primeira página" in p_img
    assert "Use a imagem da primeira página" not in p_txt
    assert "sem imagem anexada" in p_txt


def test_mesclar_campos_fallback_imagem_prevalece_preservando_cnpj_cpf_nativo_valido():
    texto = {
        "cnpj_prestadora": "11.222.333/0001-81",
        "cpf": "529.982.247-25",
        "nome": "Nome Quebrado",
        "competencia": "2025-02",
    }
    # Quando a imagem traz valores completos e válidos (inclusive outro CNPJ válido), a imagem prevalece
    imagem_ok = {
        "cnpj_prestadora": "33.000.167/0001-01",
        "cpf": "529.982.247-25",
        "nome": "Maria Aparecida Souza",
        "data_exame": "2025-03-15",
        "tipo_exame": "periodico",
    }
    mesclado = extracao._mesclar_campos_fallback(texto, imagem_ok)
    assert mesclado["cnpj_prestadora"] == "33.000.167/0001-01"
    assert mesclado["nome"] == "Maria Aparecida Souza"
    assert mesclado["data_exame"] == "2025-03-15"
    assert mesclado["competencia"] == "2025-02"

    # Quando a imagem devolve CNPJ/CPF com dígito inválido, preserva os válidos vindos do texto nativo
    imagem_digito_ruim = {
        "cnpj_prestadora": "11.222.333/0001-00",
        "cpf": "529.982.247-00",
        "nome": "Maria Aparecida Souza",
        "data_exame": "2025-03-15",
    }
    mesclado_preservado = extracao._mesclar_campos_fallback(texto, imagem_digito_ruim)
    assert mesclado_preservado["cnpj_prestadora"] == "11.222.333/0001-81"
    assert mesclado_preservado["cpf"] == "529.982.247-25"
    assert mesclado_preservado["nome"] == "Maria Aparecida Souza"
    assert mesclado_preservado["data_exame"] == "2025-03-15"


def test_extracao_pagina_nativa_completa_nao_envia_imagem_ao_gemini(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("holerite", texto_nativo=True)
    chamadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        chamadas.append((prompt, imagem_png))
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

    assert [img for _, img in chamadas] == [None]  # 1 única chamada e sem imagem PNG!
    assert "Use a imagem da primeira página" not in chamadas[0][0]
    assert "sem imagem anexada" in chamadas[0][0]
    campos = _campos_banco(doc_id)
    assert campos["cnpj_prestadora"] == "11.222.333/0001-81"
    assert campos["competencia"] == "2025-03"
    assert _origens_banco(doc_id) == {f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO_TEXTO}"}


def test_extracao_pagina_nativa_incompleta_faz_fallback_automatico_com_imagem(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("aso", texto_nativo=True)
    chamadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        chamadas.append((prompt, imagem_png))
        if imagem_png is None:
            # 1ª tentativa (só texto): faltou data_exame e tipo_exame (ex.: estavam em carimbo/checkbox na imagem)
            parcial = {
                "cnpj_prestadora": "11.222.333/0001-81",
                "nome": "Maria",
                "cpf": "529.982.247-25",
            }
            return {"candidates": [{"content": {"parts": [{"text": json.dumps(parcial)}]}}]}
        # 2ª tentativa (fallback com imagem): Gemini Vision lê o carimbo, o checkbox e corrige o nome completo
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

    assert [img for _, img in chamadas] == [None, b"PNG_BYTES_FICTICIOS"]
    assert "sem imagem anexada" in chamadas[0][0]
    assert "Use a imagem da primeira página" in chamadas[1][0]
    campos = _campos_banco(doc_id)
    assert campos["data_exame"] == "2025-03-15"
    assert campos["tipo_exame"] == "periodico"
    assert campos["nome"] == "Maria Silva"  # resposta com imagem prevaleceu
    assert _origens_banco(doc_id) == {f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO}"}


def test_extracao_pagina_escaneada_envia_imagem_direto_na_primeira_chamada(criar_doc_extracao, monkeypatch):
    doc_id = criar_doc_extracao("aso", texto_nativo=False)
    chamadas = []

    def falso_gemini(prompt, schema, imagem_png=None, **kw):
        chamadas.append((prompt, imagem_png))
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

    assert [img for _, img in chamadas] == [b"PNG_BYTES_FICTICIOS"]
    assert "Use a imagem da primeira página" in chamadas[0][0]
    assert _origens_banco(doc_id) == {f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO}"}


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


def test_processar_paginas_lote_roda_pymupdf_sequencial_e_tesseract_so_em_escaneadas(tmp_path, monkeypatch):
    """_processar_paginas_lote abre fitz uma única vez na thread chamadora e roda Tesseract só nas escaneadas."""
    doc = fitz.open()
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "HOLERITE MENSAL - FOLHA DE PAGAMENTO INDIVIDUAL", fontsize=12)
    p1.insert_text((50, 96), "Empregador: Servicos Horizonte Ltda CNPJ 11.222.333/0001-81", fontsize=12)
    p1.insert_text((50, 120), "Empregado: Joao Carlos Pereira CPF 529.982.247-25 Competencia 03/2025", fontsize=12)

    p2 = doc.new_page(width=595, height=842)
    buf = io.BytesIO()
    Image.new("RGB", (600, 850), "white").save(buf, format="PNG")
    p2.insert_image(p2.rect, stream=buf.getvalue())

    p3 = doc.new_page(width=595, height=842)
    p3.insert_text((50, 72), "ATESTADO DE SAUDE OCUPACIONAL - EXAME PERIODICO", fontsize=12)
    p3.insert_text((50, 96), "Empregador: Servicos Horizonte Ltda CNPJ 11.222.333/0001-81", fontsize=12)
    p3.insert_text((50, 120), "Empregado: Maria Aparecida Souza CPF 529.982.247-25 Parecer APTO", fontsize=12)

    pdf = tmp_path / "lote_misto_3p.pdf"
    doc.save(str(pdf))
    doc.close()

    thread_principal = threading.get_ident()
    aberturas_fitz = []
    fitz_open_real = fitz.open

    def rastrear_fitz_open(*args, **kwargs):
        aberturas_fitz.append(threading.get_ident())
        return fitz_open_real(*args, **kwargs)

    paginas_tesseract = []
    limpezas_cache = []
    orig_limpar = ocr._limpar_cache_fitz

    def rastrear_limpeza():
        limpezas_cache.append(True)
        orig_limpar()

    monkeypatch.setattr(ocr.fitz, "open", rastrear_fitz_open)
    monkeypatch.setattr(ocr, "_limpar_cache_fitz", rastrear_limpeza)
    monkeypatch.setattr(ocr, "ocr_imagem", lambda png: (paginas_tesseract.append(png.name) or "OCR pagina 2"))

    resultados = ocr._processar_paginas_lote(pdf, tmp_path, 3)

    assert aberturas_fitz == [thread_principal]  # 1 única abertura sequencial na thread chamadora
    assert len(limpezas_cache) >= 3  # cache interno do MuPDF liberado para conter picos de RAM
    assert [n for n, _, _ in resultados] == [1, 2, 3]
    assert [nat for _, _, nat in resultados] == [True, False, True]
    assert "Joao Carlos Pereira" in resultados[0][1]
    assert resultados[1][1] == "OCR pagina 2"
    assert "Maria Aparecida Souza" in resultados[2][1]
    assert paginas_tesseract == ["pag_0002.png"]
    for n in (1, 2, 3):
        assert (tmp_path / f"pag_{n:04d}.png").is_file()


def test_reextrair_campos_aceita_versao_texto_nativo_como_atual():
    lote_id = None
    try:
        with psycopg.connect(config.DATABASE_URL) as conn:
            lote_id = conn.execute(
                "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 'r.pdf', 'concluido') RETURNING id",
                (uuid.uuid4().hex + uuid.uuid4().hex,),
            ).fetchone()[0]

            def _criar(ordem, origem):
                doc_id = conn.execute(
                    "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo, estado) "
                    "VALUES (%s, %s, %s, %s, 'holerite', 'classificado') RETURNING id",
                    (lote_id, ordem, ordem, ordem),
                ).fetchone()[0]
                if origem:
                    conn.execute(
                        "INSERT INTO documento_campos (documento_id, campo, valor, origem) "
                        "VALUES (%s, 'nome', 'Maria', %s)",
                        (doc_id, origem),
                    )
                return doc_id

            doc_antigo = _criar(1, "gemini:gemini-extracao-v3")
            doc_img_atual = _criar(2, f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO}")
            doc_txt_atual = _criar(3, f"gemini:{prompts.VERSAO_PROMPT_EXTRACAO_TEXTO}")
            doc_sem = _criar(4, None)

            versoes_atuais = (prompts.VERSAO_PROMPT_EXTRACAO, prompts.VERSAO_PROMPT_EXTRACAO_TEXTO)
            sel = dict(reextrair_campos.selecionar(conn, versoes_atuais, lote=lote_id))
            assert sel == {doc_antigo: "gemini-extracao-v3", doc_sem: reextrair_campos.SEM_EXTRACAO}
            assert doc_img_atual not in sel
            assert doc_txt_atual not in sel
    finally:
        if lote_id is not None:
            with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
                conn.execute("DELETE FROM lote WHERE id = %s", (lote_id,))


