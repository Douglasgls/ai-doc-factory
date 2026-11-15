from app.extracao import limpar
from app.renomeacao import (
    gerar_nome_padronizado,
    normalizar_competencia,
    normalizar_tipo_exame,
    resolver_colisoes_nomes,
    slugificar,
)


def test_slugificar_remove_acentos_e_normaliza_snake_case():
    assert slugificar("Douglas Paz da Penha") == "douglas_paz_da_penha"
    assert slugificar("João Antônio — S/A Ltda.") == "joao_antonio_s_a_ltda"


def test_normalizar_competencia_aceita_varios_formatos():
    assert normalizar_competencia("2026-03") == "2026-03"
    assert normalizar_competencia("03/2026") == "2026-03"
    assert normalizar_competencia("Março de 2026") == "2026-03"
    assert normalizar_competencia("dez/2025") == "2025-12"
    assert normalizar_competencia("2026-13") is None
    assert normalizar_competencia("invalido") is None


def test_aso_inclui_nome_data_e_tipo_exame():
    nome = gerar_nome_padronizado(
        "aso",
        {"nome": "Douglas Paz", "data_exame": "12/03/2026", "tipo_exame": "Admissional"},
    )
    assert nome == "aso_douglas_paz_2026-03-12_admissional.pdf"
    assert normalizar_tipo_exame("Periódico") == "periodico"
    assert normalizar_tipo_exame("Mudança de Risco Ocupacional") == "mudanca_risco"


def test_folha_pagamento_usa_empresa_e_competencia_sem_funcionario():
    nome = gerar_nome_padronizado(
        "folha_pagamento",
        {
            "nome_empresa": "Empresa ABC",
            "nome": "Funcionario Qualquer",
            "competencia": "Março de 2026",
        },
    )
    assert nome == "folha_pagamento_empresa_abc_2026-03.pdf"


def test_folha_ponto_mensal_e_periodo_parcial():
    mensal = gerar_nome_padronizado(
        "folha_ponto",
        {"nome_funcionario": "Douglas Paz", "competencia": "2026-03"},
    )
    parcial = gerar_nome_padronizado(
        "folha_ponto",
        {
            "nome_funcionario": "Douglas Paz",
            "inicio_periodo": "2026-03-15",
            "fim_periodo": "2026-04-14",
        },
    )
    assert mensal == "folha_ponto_douglas_paz_2026-03.pdf"
    assert parcial == "folha_ponto_douglas_paz_2026-03-15_a_2026-04-14.pdf"


def test_holerite_nao_expoe_cpf_e_inclui_competencia():
    nome = gerar_nome_padronizado(
        "holerite",
        {
            "nome": "Douglas Paz da Penha",
            "cpf": "123.456.789-00",
            "competencia": "03/2026",
        },
    )
    assert nome == "holerite_douglas_paz_da_penha_2026-03.pdf"
    assert "123" not in nome


def test_recibo_ferias_usa_periodo_gozo():
    nome = gerar_nome_padronizado(
        "recibo_ferias",
        {
            "nome": "Douglas Paz",
            "inicio_ferias": "2026-07-01",
            "fim_ferias": "2026-07-30",
        },
    )
    assert nome == "recibo_ferias_douglas_paz_2026-07-01_a_2026-07-30.pdf"


def test_atestado_medico_nao_expoe_cid():
    nome = gerar_nome_padronizado(
        "atestado_medico",
        {
            "nome": "Douglas Paz",
            "data_emissao": "2026-03-12",
            "cid": "J11",
        },
    )
    assert nome == "atestado_medico_douglas_paz_2026-03-12.pdf"
    assert "j11" not in nome


def test_contrato_e_aditivo():
    contrato = gerar_nome_padronizado(
        "contrato_trabalho",
        {"nome": "Douglas Paz", "data_admissao": "2026-02-05"},
    )
    aditivo = gerar_nome_padronizado(
        "aditivo_contratual",
        {"nome": "Douglas Paz", "data_admissao": "2026-08-10"},
    )
    assert contrato == "contrato_trabalho_douglas_paz_2026-02-05.pdf"
    assert aditivo == "aditivo_contratual_douglas_paz_2026-08-10.pdf"


def test_fallback_sem_campos_validos():
    assert gerar_nome_padronizado("holerite", {}, documento_id=42) == "holerite_42.pdf"
    assert gerar_nome_padronizado(None, {}, documento_id=7, nome_original="Holerite 123.pdf") == "holerite_123.pdf"


def test_resolver_colisoes_nomes_repetidos():
    resolvidos = resolver_colisoes_nomes(
        [
            (10, "holerite_douglas_paz_2026-03.pdf"),
            (11, "holerite_douglas_paz_2026-03.pdf"),
            (12, "holerite_douglas_paz_2026-02.pdf"),
        ]
    )
    assert resolvidos[10] == "holerite_douglas_paz_2026-03_01.pdf"
    assert resolvidos[11] == "holerite_douglas_paz_2026-03_02.pdf"
    assert resolvidos[12] == "holerite_douglas_paz_2026-02.pdf"


def test_limpar_extracao_valida_competencia_e_tipo_exame():
    limpos = limpar(
        {
            "nome": "Douglas Paz",
            "competencia": "Março de 2026",
            "tipo_exame": "Periódico",
            "data_emissao": "12/03/2026",
            "inicio_ferias": "data_invalida",
        }
    )
    assert limpos["nome"] == "Douglas Paz"
    assert limpos["competencia"] == "2026-03"
    assert limpos["tipo_exame"] == "periodico"
    assert limpos["data_emissao"] == "2026-03-12"
    assert "inicio_ferias" not in limpos


def test_rota_download_documento_retorna_pdf_e_content_disposition(monkeypatch):
    from fastapi.testclient import TestClient
    from app.api import app
    from app.escopo import documento_para_leitura
    from app.routers.documentos import actions as doc_actions

    monkeypatch.setattr(
        doc_actions,
        "download_documento",
        lambda session, doc_id: (b"%PDF-1.4\n%mock\n", "holerite_douglas_paz_2026-03.pdf"),
    )
    client = TestClient(app)
    app.dependency_overrides[documento_para_leitura] = lambda: 123  # o documento 123 não existe no banco
    try:
        resp = client.get("/documentos/123/download")
    finally:
        app.dependency_overrides.pop(documento_para_leitura, None)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.headers["content-disposition"] == 'attachment; filename="holerite_douglas_paz_2026-03.pdf"'
    assert resp.content.startswith(b"%PDF-1.4")


def test_rota_download_documento_inexistente_retorna_404():
    from fastapi.testclient import TestClient
    from app.api import app

    client = TestClient(app)
    resp = client.get("/documentos/99999999/download")
    assert resp.status_code == 404




def _lote_com_folha_pagamento(db, contrato_id, competencia="2026-03"):
    """Lote com um documento folha_pagamento sem nome de empresa extraído (só a competência)."""
    import uuid

    lote = db.execute("INSERT INTO lote (sha256, nome_arquivo, contrato_id) VALUES (%s, 'lote.pdf', %s) RETURNING id",
                      (uuid.uuid4().hex * 2, contrato_id)).fetchone()[0]
    doc = db.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo) "
                     "VALUES (%s, 1, 1, 1, 'folha_pagamento') RETURNING id", (lote,)).fetchone()[0]
    db.execute("INSERT INTO documento_campos (documento_id, campo, valor, origem) VALUES (%s, 'competencia', %s, 'gemini')",
               (doc, competencia))
    return lote, doc


def test_nome_usa_prestador_do_contrato_e_colisao_por_contrato(orgs):
    """Sem nome de empresa extraído, a folha de pagamento leva a razão social do prestador do contrato do lote; a
    numeração de colisão vale entre lotes do mesmo contrato e não entre contratos diferentes."""
    from app.renomeacao import atualizar_nome_padronizado

    db = orgs.db
    c1, c2 = orgs.contrato(), orgs.contrato()
    razao = db.execute("SELECT p.razao_social FROM contrato c JOIN prestador p ON p.id = c.prestador_id "
                       "WHERE c.id = %s", (c1,)).fetchone()[0]
    _, d1 = _lote_com_folha_pagamento(db, c1)
    _, d2 = _lote_com_folha_pagamento(db, c1)
    _, d3 = _lote_com_folha_pagamento(db, c2)

    n1 = atualizar_nome_padronizado(db, d1)
    assert n1 == f"folha_pagamento_{slugificar(razao)}_2026-03.pdf"
    n2 = atualizar_nome_padronizado(db, d2)
    nomes = dict(db.execute("SELECT id, nome_padronizado FROM documento WHERE id = ANY(%s)", ([d1, d2],)).fetchall())
    stem = n1[:-4]
    assert nomes == {d1: f"{stem}_01.pdf", d2: f"{stem}_02.pdf"} and n2 == f"{stem}_02.pdf"
    assert not atualizar_nome_padronizado(db, d3).endswith("_01.pdf")  # outro contrato: sem colisão


def test_nome_sem_contrato_nao_quebra(orgs):
    from app.renomeacao import atualizar_nome_padronizado

    lote, doc = _lote_com_folha_pagamento(orgs.db, None)
    try:
        assert atualizar_nome_padronizado(orgs.db, doc) == "folha_pagamento_2026-03.pdf"
    finally:
        orgs.db.execute("DELETE FROM lote WHERE id = %s", (lote,))
