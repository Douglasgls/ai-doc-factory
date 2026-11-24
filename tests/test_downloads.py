from urllib.parse import unquote

from app.downloads import content_disposition


def _partes(cabecalho):
    tipo, ascii_, estendido = [p.strip() for p in cabecalho.split(";")]
    return tipo, ascii_, estendido


def test_nome_simples():
    assert content_disposition("holerite_ana_2026-03.pdf") == (
        'attachment; filename="holerite_ana_2026-03.pdf"; filename*=UTF-8\'\'holerite_ana_2026-03.pdf')


def test_acento_vira_ascii_e_utf8_percent_encoded():
    h = content_disposition("Folha de Pagamento - João Conceição.pdf")
    assert 'filename="Folha de Pagamento - Joao Conceicao.pdf"' in h
    assert "filename*=UTF-8''Folha%20de%20Pagamento%20-%20Jo%C3%A3o%20Concei%C3%A7%C3%A3o.pdf" in h
    h.encode("ascii")  # o cabeçalho inteiro é ASCII


def test_espaco():
    h = content_disposition("meu arquivo.pdf")
    assert 'filename="meu arquivo.pdf"' in h and "filename*=UTF-8''meu%20arquivo.pdf" in h


def test_aspas_nao_quebram_o_cabecalho():
    h = content_disposition('a"b.pdf')
    _, ascii_, estendido = _partes(h)
    assert ascii_ == 'filename="a_b.pdf"'
    assert unquote(estendido.split("''", 1)[1]) == 'a"b.pdf'
    assert estendido.count('"') == 0 and "%22" in estendido


def test_barras_nao_viram_caminho():
    h = content_disposition(r"../../etc/passwd\x.pdf")
    _, ascii_, estendido = _partes(h)
    assert ascii_ == 'filename="x.pdf"'
    assert estendido == "filename*=UTF-8''x.pdf"


def test_quebra_de_linha_e_controle_removidos():
    h = content_disposition("a\r\nSet-Cookie: x.pdf")
    assert "\r" not in h and "\n" not in h


def test_nome_so_com_simbolos_ou_vazio_cai_num_padrao():
    assert 'filename="arquivo"' in content_disposition("")
    assert 'filename="arquivo"' in content_disposition("日本語")
    assert "filename*=UTF-8''%E6%97%A5%E6%9C%AC%E8%AA%9E" in content_disposition("日本語")


def test_rota_download_com_acento_e_aspas(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import app
    from app.escopo import documento_para_leitura
    from app.routers.documentos import actions as doc_actions

    monkeypatch.setattr(doc_actions, "download_documento",
                        lambda session, doc_id: (b"%PDF-1.4\n", 'ASO - José "Zé" Souza.pdf'))
    app.dependency_overrides[documento_para_leitura] = lambda: 1
    try:
        resp = TestClient(app).get("/documentos/1/download")
    finally:
        app.dependency_overrides.pop(documento_para_leitura, None)
    assert resp.status_code == 200
    h = resp.headers["content-disposition"]
    assert 'filename="ASO - Jose _Ze_ Souza.pdf"' in h
    assert unquote(h.split("filename*=UTF-8''", 1)[1]) == 'ASO - José "Zé" Souza.pdf'
