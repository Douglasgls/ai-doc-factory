"""Schemas de saída (response_model): a resposta HTTP valida contra o modelo e é idêntica ao que a action devolve.
Se o modelo descartasse um campo, a igualdade com a saída crua da action falharia. Postgres/Redis do compose; sem rede."""
import json
import uuid

import psycopg
import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.testclient import TestClient

from app import analise, config, ponto
from app.api import app
from app.campos import gravar_campo
from app.routers.busca import actions as busca_actions
from app.routers.busca.schemas import ResultadoBuscaOut
from app.routers.cadastro_empresas import actions as cad_actions
from app.routers.cadastro_empresas.schemas import EmpresaOut
from app.routers.documentos import actions as doc_actions
from app.routers.documentos.schemas import AnalisePontoOut, DocumentoOut, DocumentosAgrupadosOut
from app.routers.empresas import actions as emp_actions
from app.routers.empresas.schemas import ConformidadeEmpresaOut, ConformidadeLoteOut, EmpresaResumoOut
from app.routers.lotes import actions as lote_actions
from app.routers.lotes.schemas import LoteCriadoOut, LoteOut
from app.routers.revisao import actions as rev_actions
from app.routers.revisao.schemas import ItemFilaRevisaoOut, RevisaoOut
from app.routers.tipos.schemas import TipoOut

client = TestClient(app)
CNPJ = "12345678000195"
CPF = "52998224725"
MARCACOES = [{"data": "2025-11-03", "pares": [["08:00", "12:00"], ["12:30", "20:30"]]},
             {"data": "2025-11-04", "pares": [["08:00", "12:00"], ["13:00", "17:00"]]}]


def _crua(valor):
    """O que o FastAPI devolveria sem response_model."""
    return json.loads(json.dumps(jsonable_encoder(valor)))


def _campos(**extra):
    return {"cnpj_prestadora": CNPJ, "razao_social_prestadora": "Alfa Ltda", "distingue_prestadora": "true",
            "nome": "Maria Silva", "cpf": CPF, "data_exame": "2999-01-01", **extra}


@pytest.fixture
def cenario(monkeypatch):
    """Lote com ASO vencido, holerite com nome divergente (mesmo CPF), folha de ponto, documento em revisão
    e documento só segmentado (sem empresa). Devolve (lote_id, [ids])."""
    docs = [("aso", "classificado", _campos(data_exame="2000-01-01")),
            ("holerite", "classificado", _campos(nome="Mario Silva")),
            ("folha_ponto", "classificado", _campos()),
            ("recibo_ferias", "em_revisao", _campos()),
            ("holerite", "segmentado", {})]
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 'schemas.pdf', 'concluido') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        ids = []
        for n, (tipo, estado, campos) in enumerate(docs, start=1):
            i = conn.execute(
                "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo, estado, confianca, probabilidades,"
                " motivo_revisao) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (lote, n, n, n, tipo, estado, 0.9 if estado != "segmentado" else None,
                 psycopg.types.json.Jsonb({tipo: 0.9}) if estado != "segmentado" else None,
                 "confiança baixa" if estado == "em_revisao" else None)).fetchone()[0]
            conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, %s, %s, %s)",
                         (lote, n, i, f"{tipo} Maria Silva CPF 529.982.247-25 schemasunico"))
            for k, v in campos.items():
                gravar_campo(conn, i, k, v, "teste")
            ids.append(i)
    yield lote, ids
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def _analisar_ponto(monkeypatch, doc_id):
    """Grava uma análise concluída (Gemini e Jev substituídos), sem rede."""
    dado = {"marcacoes": MARCACOES, "intervalo_pre_assinalado": False, "analise": "Folha com horas extras.",
            "divergencias": [{"tipo": "horas_extras_acima_limite", "data": "2025-11-03", "minutos": 120}],
            "horario_contratual": [], "totais_declarados": {"total_horas_min": None, "horas_extras_min": None}}
    monkeypatch.setattr(analise, "extrair_com_gemini", lambda *a, **k: (dado, "gemini-teste", {"promptTokenCount": 1}))
    respostas = {d: {"score": 2.0 if d == "horas_extras" else 0.0, "confianca": 0.9, "n_niveis": 4,
                     "probabilidades": {"0": 0.0, "1": 0.0, "2": 1.0, "3": 0.0}}
                 for d in ("horas_extras", "intervalos", "descanso", "registro")}
    monkeypatch.setattr(analise, "julgar_com_jev", lambda *a, **k: (respostas, "jev-teste", {"cost": 0.1}))
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        perfil = ponto.carregar_perfil(conn)
        resultado = analise.analisar("texto", [], perfil)
        resultado["perfil"] = perfil
        analise._gravar(conn, doc_id, "concluida", resultado)


def _confere(url, modelo, crua, **kw):
    r = client.get(url)
    assert r.status_code == 200, r.text
    corpo = r.json()
    if isinstance(corpo, list):
        for item in corpo:
            modelo.model_validate(item)
    else:
        modelo.model_validate(corpo)
    assert corpo == _crua(crua), f"{url}: a resposta difere da saída da action (campo descartado ou alterado?)"
    return corpo


def test_saude_e_tipos():
    assert client.get("/health").json() == {"status": "ok"}
    tipos = client.get("/tipos").json()
    assert [t["slug"] for t in tipos] == list(config.TIPOS_INFO)
    for t in tipos:
        TipoOut.model_validate(t)


def test_upload_de_lote():
    pdf = b"%PDF-1.4 " + uuid.uuid4().hex.encode()
    r = client.post("/lotes", files={"arquivo": ("a.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    lote = r.json()["lote_id"]
    try:
        LoteCriadoOut.model_validate(r.json())
        assert r.json() == {"lote_id": lote, "estado": "recebido", "existente": False, "empresa_id": None}
        r2 = client.post("/lotes", files={"arquivo": ("a.pdf", pdf, "application/pdf")})
        assert r2.json()["existente"] is True and r2.json()["lote_id"] == lote
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_lote_busca_documentos(cenario):
    lote, ids = cenario
    corpo = _confere(f"/lotes/{lote}", LoteOut, lote_actions.obter_lote(lote))
    assert [d["id"] for d in corpo["documentos"]] == ids
    assert corpo["documentos"][-1]["confianca"] is None  # segmentado: nulos preservados

    achados = _confere("/busca?q=schemasunico&limite=100", ResultadoBuscaOut,
                       [r for r in busca_actions.buscar("schemasunico", 100)])
    assert {a["documento_id"] for a in achados} >= set(ids)
    assert "529.982.247-25" not in json.dumps(achados)  # anonimização preservada

    doc = _confere(f"/documentos/{ids[0]}", DocumentoOut, doc_actions.obter_documento(ids[0]))
    assert "529.982.247-25" not in doc["paginas"][0]["texto"]
    assert doc["campos"]["cpf"] != CPF and doc["pessoa"] == "Maria Silva"

    grupos = client.get("/documentos")
    assert grupos.status_code == 200
    DocumentosAgrupadosOut.model_validate(grupos.json())
    assert grupos.json() == _crua(doc_actions.listar_documentos())


def test_revisao_e_correcoes(cenario, extracoes):
    lote, ids = cenario
    fila = _confere("/revisao", ItemFilaRevisaoOut, rev_actions.fila_revisao())
    assert ids[3] in {i["id"] for i in fila}

    r = client.post(f"/documentos/{ids[3]}/revisao", json={"tipo": "atestado_medico", "revisor": "ana"})
    assert r.status_code == 200
    RevisaoOut.model_validate(r.json())
    assert set(r.json()) == {"id", "estado", "tipo", "tipo_original", "revisor", "revisado_em"}
    assert r.json()["tipo_original"] == "recibo_ferias" and r.json()["estado"] == "revisado"

    r = client.patch(f"/documentos/{ids[1]}/tipo", json={"tipo": "aso", "revisor": "ana"})
    assert r.status_code == 200
    DocumentoOut.model_validate(r.json())
    assert r.json() == _crua(doc_actions.obter_documento(ids[1]))

    r = client.put(f"/documentos/{ids[0]}/campos", json={"campos": {"nome": "Outra Pessoa"}, "revisor": "ana"})
    assert r.status_code == 200
    DocumentoOut.model_validate(r.json())
    assert r.json()["campos"]["nome"] == "Outra Pessoa" and r.json() == _crua(doc_actions.obter_documento(ids[0]))


def test_conformidade(cenario):
    lote, ids = cenario
    emp = _confere(f"/empresas/{CNPJ}/conformidade", ConformidadeEmpresaOut, emp_actions.conformidade_empresa(CNPJ))
    regras = {(d["criterio"], d["regra"]) for d in emp["geral"]["descontos"]}
    assert ("validade", "documento_vencido") in regras and ("consistencia", "campo_divergente") in regras
    # chaves condicionais: presentes só onde o cálculo as produz
    assert "bons" in emp["geral"]["criterios"]["completude"]
    vencido = next(d for d in emp["geral"]["descontos"] if d["regra"] == "documento_vencido")
    assert "valores" not in vencido and "campo" not in vencido
    diverg = next(d for d in emp["geral"]["descontos"] if d["regra"] == "campo_divergente")
    assert diverg["campo"] == "nome" and diverg["conferir"] is True and len(diverg["valores"]) == 3

    resumos = _confere("/empresas", EmpresaResumoOut, emp_actions.listar_empresas())
    assert CNPJ in {e["cnpj"] for e in resumos}

    corpo = _confere(f"/lotes/{lote}/conformidade", ConformidadeLoteOut, emp_actions.conformidade_lote(lote))
    assert [s["documento"] for s in corpo["sem_empresa"]] == [ids[4]]
    assert corpo["empresas"][0]["documentos"] == sorted(ids[:4])


def test_analise_ponto(cenario, monkeypatch):
    lote, ids = cenario
    pendente = client.get(f"/documentos/{ids[2]}/analise-ponto")
    assert pendente.status_code == 200 and pendente.json() == {"documento_id": ids[2], "estado": "pendente"}

    _analisar_ponto(monkeypatch, ids[2])
    corpo = _confere(f"/documentos/{ids[2]}/analise-ponto", AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert corpo["estado"] == "concluida" and corpo["score_geral"] == pytest.approx(2 / 3)
    assert corpo["divergencias"][0]["base_legal"] and set(corpo["scores_dimensao"]) == {
        "horas_extras", "intervalos", "descanso", "registro"}
    assert client.get(f"/documentos/{ids[0]}/analise-ponto").status_code == 404  # não é folha de ponto


def test_cadastro_empresas():
    nome = "Schemas " + uuid.uuid4().hex[:8]
    r = client.post("/cadastro-empresas", json={"nome": nome})
    assert r.status_code == 201
    EmpresaOut.model_validate(r.json())
    empresa_id = r.json()["id"]
    try:
        assert client.get(f"/cadastro-empresas/{empresa_id}").json() == _crua(cad_actions.obter_empresa(empresa_id))
        lista = client.get("/cadastro-empresas").json()
        assert lista == _crua(cad_actions.listar_empresas())
        assert nome in {e["nome"] for e in lista}
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def test_openapi_expoe_os_modelos():
    esquemas = client.get("/openapi.json").json()["components"]["schemas"]
    for nome in ("SaudeOut", "TipoOut", "ResultadoBuscaOut", "LoteCriadoOut", "LoteOut", "ConformidadeEmpresaOut",
                 "ConformidadeLoteOut", "EmpresaResumoOut", "DocumentoOut", "DocumentosAgrupadosOut",
                 "AnalisePontoOut", "ItemFilaRevisaoOut", "RevisaoOut", "EmpresaOut"):
        assert nome in esquemas, nome
