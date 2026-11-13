"""Schemas de saída (response_model): a resposta HTTP valida contra o modelo e é idêntica ao que a action devolve.
Se o modelo descartasse um campo, a igualdade com a saída crua da action falharia. Postgres/Redis do compose; sem rede.

Blindagem: toda rota JSON com response_model precisa constar em COMPARACOES, com os testes que comparam a resposta
com a saída da action (`_confere`/`_confere_resposta`, sempre com o rótulo literal "METODO /caminho"). A varredura
no fim do arquivo falha se uma rota nova entrar sem teste, ou se o teste citado não existir ou não citar a rota."""
import inspect
import json
import sys
import uuid
from dataclasses import asdict

import psycopg
import pytest
from fastapi.encoders import jsonable_encoder
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app import analise, config, eventos, ponto, senhas
from app.api import app
from app.campos import gravar_campo
from app.routers import r as redis_cliente
from app.routers.auth import actions as auth_actions
from app.routers.auth.schemas import TokenOut, UsuarioOut
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
from app.routers.revisao.schemas import ItemFilaRevisaoOut, Revisao, RevisaoOut
from app.routers.tipos import actions as tipos_actions
from app.routers.tipos.schemas import TipoOut

client = TestClient(app)
CNPJ = "12345678000195"
CPF = "52998224725"
CNPJ_B, CPF_B = "11222333000181", "11144477735"
MARCACOES = [{"data": "2025-11-03", "pares": [["08:00", "12:00"], ["12:30", "20:30"]]},
             {"data": "2025-11-04", "pares": [["08:00", "12:00"], ["13:00", "17:00"]]}]


def _crua(valor):
    """O que o FastAPI devolveria sem response_model."""
    return json.loads(json.dumps(jsonable_encoder(valor)))


def _campos(**extra):
    return {"cnpj_prestadora": CNPJ, "razao_social_prestadora": "Alfa Ltda", "distingue_prestadora": "true",
            "nome": "Maria Silva", "cpf": CPF, "rg": "12.345.678-9", "pis": "123.45678.90-1",
            "data_exame": "2999-01-01", **extra}


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


SETE_DIAS = ["2025-11-03", "2025-11-04", "2025-11-05", "2025-11-06", "2025-11-07", "2025-11-08", "2025-11-09"]
SEMANA_COMPLETA = [{"data": d, "pares": [["08:00", "12:00"], ["13:00", "18:00"]]} for d in SETE_DIAS]


def _analisar_ponto(monkeypatch, doc_id, marcacoes=MARCACOES, confianca_intervalos=0.9, **extra_gemini):
    """Grava uma análise concluída (Gemini e Jev substituídos), sem rede. Reexecutar substitui a linha."""
    dado = {"marcacoes": marcacoes, "intervalo_pre_assinalado": False, "analise": "Folha com horas extras.",
            "divergencias": [{"tipo": "horas_extras_acima_limite", "data": "2025-11-03", "minutos": 120}],
            "horario_contratual": [], "totais_declarados": {"total_horas_min": None, "horas_extras_min": None},
            **extra_gemini}
    monkeypatch.setattr(analise, "extrair_com_gemini", lambda *a, **k: (dado, "gemini-teste", {"promptTokenCount": 1}))

    def jev(contagens, texto, nao_avaliadas=()):  # como o real: não pergunta as dimensões sem dados
        respostas = {d: {"score": 2.0 if d == "horas_extras" else 0.0,
                         "confianca": confianca_intervalos if d == "intervalos" else 0.9, "n_niveis": 4,
                         "probabilidades": {"0": 0.0, "1": 0.0, "2": 1.0, "3": 0.0}}
                     for d in ("horas_extras", "intervalos", "descanso", "registro") if d not in nao_avaliadas}
        return respostas, "jev-teste", {"cost": 0.1}
    monkeypatch.setattr(analise, "julgar_com_jev", jev)
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        perfil = ponto.carregar_perfil(conn)
        resultado = analise.analisar("texto", [], perfil)
        resultado["perfil"] = perfil
        analise._gravar(conn, doc_id, "concluida", resultado)
    return resultado


def _rotas_com_modelo():
    return {(m, rt.path) for rt in app.routes if isinstance(rt, APIRoute) and rt.response_model is not None
            for m in rt.methods}


_ROTAS_COM_MODELO = _rotas_com_modelo()


def _confere_resposta(rota, resposta, crua, modelo=None, status=200, ignorar=()):
    """Compara a resposta HTTP com a saída da action. `rota` é o rótulo literal "METODO /caminho" (a varredura
    no fim do arquivo exige que ele apareça no código do teste). `ignorar`: chaves de primeiro nível voláteis."""
    metodo, caminho = rota.split(" ", 1)
    assert (metodo, caminho) in _ROTAS_COM_MODELO, f"rota desconhecida ou sem response_model: {rota}"
    assert resposta.status_code == status, f"{rota}: {resposta.status_code} {resposta.text}"
    corpo = resposta.json()
    if modelo is not None:
        for item in corpo if isinstance(corpo, list) else [corpo]:
            modelo.model_validate(item)
    esperado = _crua(crua)
    if ignorar:
        corpo = {k: v for k, v in corpo.items() if k not in ignorar}
        esperado = {k: v for k, v in esperado.items() if k not in ignorar}
    assert corpo == esperado, f"{rota}: a resposta difere da saída da action (campo descartado ou alterado?)"
    return resposta.json()


def _confere(rota, url, modelo, crua):
    return _confere_resposta(rota, client.get(url), crua, modelo)


@pytest.fixture
def limpar_eventos():
    lotes = []
    yield lotes
    for lote in lotes:
        redis_cliente.delete(eventos._chave_progresso(lote), eventos._chave_historico(lote))


def test_saude_e_tipos():
    assert _confere("GET /health", "/health", None, {"status": "ok"}) == {"status": "ok"}
    tipos = _confere("GET /tipos", "/tipos", TipoOut, tipos_actions.listar_tipos())
    assert [t["slug"] for t in tipos] == list(config.TIPOS_INFO)


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
        assert "reprocessando" not in r2.json()  # chave condicional: ausente fora do reenvio de lote em erro
        _confere_resposta("POST /lotes", r2, lote_actions.criar_lote(pdf, pdf, "a.pdf"), LoteCriadoOut)
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_reenvio_de_lote_em_erro_devolve_reprocessando(monkeypatch):
    monkeypatch.setattr(lote_actions, "enfileirar", lambda *a, **k: None)
    pdf = b"%PDF-1.4 " + uuid.uuid4().hex.encode()
    lote = lote_actions.criar_lote(pdf, pdf, "e.pdf")["lote_id"]

    def em_erro():
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("UPDATE lote SET estado = 'erro' WHERE id = %s", (lote,))
    try:
        em_erro()
        esperado = lote_actions.criar_lote(pdf, pdf, "e.pdf")  # a action reprocessa e devolve reprocessando
        assert esperado["reprocessando"] is True
        em_erro()
        r = client.post("/lotes", files={"arquivo": ("e.pdf", pdf, "application/pdf")})
        corpo = _confere_resposta("POST /lotes", r, esperado, LoteCriadoOut)
        assert corpo == {"lote_id": lote, "estado": "recebido", "existente": True, "empresa_id": None,
                         "reprocessando": True}
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_lote_com_e_sem_eventos(cenario, limpar_eventos):
    lote, ids = cenario
    limpar_eventos.append(lote)
    redis_cliente.delete(eventos._chave_progresso(lote), eventos._chave_historico(lote))
    sem = _confere("GET /lotes/{lote_id}", f"/lotes/{lote}", LoteOut, lote_actions.obter_lote(lote))
    assert sem["ultimo_evento"] is None and sem["historico_eventos"] == []

    eventos.publicar_evento(lote, "ocr", "Lendo OCR", r=redis_cliente, pagina_atual=1, total_paginas=3)
    eventos.publicar_evento(lote, "classificando", "Classificando", r=redis_cliente, documento_id=ids[0], tipo="aso",
                            estado_documento="classificado", docs_pendentes=2, total_documentos=5)
    eventos.publicar_evento(lote, "concluido", "Pronto", r=redis_cliente, segmentacao_ambigua=False,
                            extra_desconhecido="preservado")  # chave fora do schema não pode sumir
    com = _confere("GET /lotes/{lote_id}", f"/lotes/{lote}", LoteOut, lote_actions.obter_lote(lote))
    assert [e["etapa"] for e in com["historico_eventos"]] == ["ocr", "classificando", "concluido"]
    assert com["ultimo_evento"]["etapa"] == "concluido" and com["ultimo_evento"]["extra_desconhecido"] == "preservado"
    assert com["historico_eventos"][0]["pagina_atual"] == 1 and "docs_pendentes" not in com["historico_eventos"][0]


def test_lote_busca_documentos(cenario):
    lote, ids = cenario
    corpo = _confere("GET /lotes/{lote_id}", f"/lotes/{lote}", LoteOut, lote_actions.obter_lote(lote))
    assert [d["id"] for d in corpo["documentos"]] == ids
    assert corpo["documentos"][-1]["confianca"] is None  # segmentado: nulos preservados

    achados = _confere("GET /busca", "/busca?q=schemasunico&limite=100", ResultadoBuscaOut,
                       busca_actions.buscar("schemasunico", 100))
    assert {a["documento_id"] for a in achados} >= set(ids)
    assert "529.982.247-25" not in json.dumps(achados)  # anonimização preservada
    assert _confere("GET /busca", "/busca?q=palavrainexistentezzz", ResultadoBuscaOut,
                    busca_actions.buscar("palavrainexistentezzz", 20)) == []

    doc = _confere("GET /documentos/{documento_id}", f"/documentos/{ids[0]}", DocumentoOut,
                   doc_actions.obter_documento(ids[0]))
    assert "529.982.247-25" not in doc["paginas"][0]["texto"]
    assert doc["campos"]["cpf"] != CPF and doc["pessoa"] == "Maria Silva"
    assert doc["campos"]["rg"] != "12.345.678-9" and doc["campos"]["pis"] != "123.45678.90-1"  # máscara aplicada
    sem_campos = _confere("GET /documentos/{documento_id}", f"/documentos/{ids[4]}", DocumentoOut,
                          doc_actions.obter_documento(ids[4]))
    assert sem_campos["campos"] == {} and sem_campos["pessoa"] is None and sem_campos["confianca"] is None

    grupos = _confere("GET /documentos", "/documentos", DocumentosAgrupadosOut, doc_actions.listar_documentos())
    assert grupos["grupos"]
    _confere("GET /documentos", "/documentos?falhou=true", DocumentosAgrupadosOut,
             doc_actions.listar_documentos(None, True))
    _confere("GET /documentos", "/documentos?falhou=false", DocumentosAgrupadosOut,
             doc_actions.listar_documentos(None, False))


def test_revisao_e_correcoes(cenario, extracoes):
    lote, ids = cenario
    fila = _confere("GET /revisao", "/revisao", ItemFilaRevisaoOut, rev_actions.fila_revisao())
    assert ids[3] in {i["id"] for i in fila}

    r = client.post(f"/documentos/{ids[3]}/revisao", json={"tipo": "atestado_medico", "revisor": "ana"})
    corpo = _confere_resposta("POST /documentos/{documento_id}/revisao", r,
                              rev_actions.revisar_documento(ids[3], Revisao(tipo="atestado_medico", revisor="ana")),
                              RevisaoOut, ignorar=("revisado_em",))  # a segunda chamada regrava revisado_em
    assert set(corpo) == {"id", "estado", "tipo", "tipo_original", "revisor", "revisado_em"}
    assert corpo["tipo_original"] == "recibo_ferias" and corpo["estado"] == "revisado"

    r = client.patch(f"/documentos/{ids[1]}/tipo", json={"tipo": "aso", "revisor": "ana"})
    _confere_resposta("PATCH /documentos/{documento_id}/tipo", r, doc_actions.obter_documento(ids[1]), DocumentoOut)

    r = client.put(f"/documentos/{ids[0]}/campos", json={"campos": {"nome": "Outra Pessoa"}, "revisor": "ana"})
    corpo = _confere_resposta("PUT /documentos/{documento_id}/campos", r, doc_actions.obter_documento(ids[0]),
                              DocumentoOut)
    assert corpo["campos"]["nome"] == "Outra Pessoa"


@pytest.fixture
def empresa_sem_nada_analisavel():
    """Segunda empresa (outro CNPJ) só com um documento em revisão de tipo desconhecido: score nulo e provisório."""
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        lote = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 'schemas-b.pdf', 'concluido') RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
        doc = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo, estado, confianca) "
            "VALUES (%s, 1, 1, 1, 'desconhecido', 'em_revisao', 0.1) RETURNING id", (lote,)).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 1, %s, 'x')", (lote, doc))
        for k, v in _campos(cnpj_prestadora=CNPJ_B, razao_social_prestadora="Beta SA", cpf=CPF_B).items():
            gravar_campo(conn, doc, k, v, "teste")
    yield lote
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def test_conformidade(cenario, empresa_sem_nada_analisavel):
    lote, ids = cenario
    emp = _confere("GET /empresas/{cnpj:path}/conformidade", f"/empresas/{CNPJ}/conformidade", ConformidadeEmpresaOut,
                   emp_actions.conformidade_empresa(CNPJ))
    regras = {(d["criterio"], d["regra"]) for d in emp["geral"]["descontos"]}
    assert ("validade", "documento_vencido") in regras and ("consistencia", "campo_divergente") in regras
    assert emp["geral"]["pendencias"], "o cenário precisa exercitar as pendências"
    # chaves condicionais: presentes só onde o cálculo as produz
    assert "bons" in emp["geral"]["criterios"]["completude"]
    vencido = next(d for d in emp["geral"]["descontos"] if d["regra"] == "documento_vencido")
    assert "valores" not in vencido and "campo" not in vencido
    diverg = next(d for d in emp["geral"]["descontos"] if d["regra"] == "campo_divergente")
    assert diverg["campo"] == "nome" and diverg["conferir"] is True and len(diverg["valores"]) == 3
    assert diverg["cpf"] != CPF  # CPF mascarado na resposta

    b = _confere("GET /empresas/{cnpj:path}/conformidade", f"/empresas/{CNPJ_B}/conformidade", ConformidadeEmpresaOut,
                 emp_actions.conformidade_empresa(CNPJ_B))
    assert b["geral"]["score"] is None and b["geral"]["provisorio"] is True

    resumos = _confere("GET /empresas", "/empresas", EmpresaResumoOut, emp_actions.listar_empresas())
    assert {CNPJ, CNPJ_B} <= {e["cnpj"] for e in resumos}

    corpo = _confere("GET /lotes/{lote_id}/conformidade", f"/lotes/{lote}/conformidade", ConformidadeLoteOut,
                     emp_actions.conformidade_lote(lote))
    assert [s["documento"] for s in corpo["sem_empresa"]] == [ids[4]]
    assert corpo["empresas"][0]["documentos"] == sorted(ids[:4])
    _confere("GET /lotes/{lote_id}/conformidade", f"/lotes/{empresa_sem_nada_analisavel}/conformidade",
             ConformidadeLoteOut, emp_actions.conformidade_lote(empresa_sem_nada_analisavel))


def test_analise_ponto(cenario, monkeypatch):
    lote, ids = cenario
    rota = "GET /documentos/{documento_id}/analise-ponto"
    url = f"/documentos/{ids[2]}/analise-ponto"
    pendente = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert pendente == {"documento_id": ids[2], "estado": "pendente"}

    # folha só com dias úteis: o descanso semanal não é avaliado (nao_avaliada, motivo; campos do Jev nulos)
    _analisar_ponto(monkeypatch, ids[2])
    corpo = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert corpo["estado"] == "concluida" and corpo["score_geral"] == pytest.approx(2 / 3)
    assert corpo["divergencias"][0]["base_legal"] and set(corpo["scores_dimensao"]) == {
        "horas_extras", "intervalos", "descanso", "registro"}
    descanso = corpo["scores_dimensao"]["descanso"]
    assert descanso["nao_avaliada"] is True and descanso["motivo"] == "sem_semana_completa"
    assert descanso["score"] is None and descanso["probabilidades"] is None and descanso["normalizado"] is None
    assert corpo["contagens"]["nao_avaliadas"] == ["descanso"]  # lista dentro de `contagens`

    # semana completa: descanso avaliado
    _analisar_ponto(monkeypatch, ids[2], marcacoes=SEMANA_COMPLETA)
    corpo = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert corpo["contagens"]["nao_avaliadas"] == [] and corpo["scores_dimensao"]["descanso"]["score"] == 0.0

    # dimensão indeterminada (confiança baixa): normalizado nulo, revisão pedida
    _analisar_ponto(monkeypatch, ids[2], marcacoes=SEMANA_COMPLETA, confianca_intervalos=0.1)
    corpo = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert corpo["scores_dimensao"]["intervalos"]["indeterminada"] is True
    assert corpo["scores_dimensao"]["intervalos"]["normalizado"] is None and corpo["requer_revisao"] is True

    # horário contratual e totais declarados lidos da folha
    _analisar_ponto(monkeypatch, ids[2], horario_contratual=[["08:00", "12:00"], ["13:00", "17:00"]],
                    totais_declarados={"total_horas_min": 2400, "horas_extras_min": 0})
    corpo = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert corpo["totais"]["declarados"]["comparado"] is True and corpo["totais"]["horario_contratual"]

    # falha definitiva: linha em erro, sem os demais campos
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        analise._gravar(conn, ids[2], "erro", {}, erro="análise falhou após as tentativas")
    erro = _confere(rota, url, AnalisePontoOut, doc_actions.obter_analise_ponto(ids[2]))
    assert erro["estado"] == "erro" and erro["erro"] and erro["score_geral"] is None

    assert client.get(f"/documentos/{ids[0]}/analise-ponto").status_code == 404  # não é folha de ponto


def test_cadastro_empresas():
    nome = "Schemas " + uuid.uuid4().hex[:8]
    r = client.post("/cadastro-empresas", json={"nome": nome})
    empresa_id = r.json()["id"]
    try:
        _confere_resposta("POST /cadastro-empresas", r, cad_actions.obter_empresa(empresa_id), EmpresaOut, status=201)
        _confere("GET /cadastro-empresas/{empresa_id}", f"/cadastro-empresas/{empresa_id}", EmpresaOut,
                 cad_actions.obter_empresa(empresa_id))
        lista = _confere("GET /cadastro-empresas", "/cadastro-empresas", EmpresaOut, cad_actions.listar_empresas())
        assert nome in {e["nome"] for e in lista}
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def test_auth_login_e_me(auth_real):
    email = f"schemas-{uuid.uuid4().hex[:8]}@exemplo.invalid"
    senha = "senha-de-teste-schemas"
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        uid = conn.execute(
            "INSERT INTO usuario (email, nome, senha_hash, nivel, papel) VALUES (%s, 'Pessoa Schemas', %s, "
            "'plataforma', 'admin') RETURNING id", (email, senhas.gerar_hash(senha, n=2 ** 10, r=8, p=1))).fetchone()[0]
    try:
        r = client.post("/auth/login", json={"usuario": email, "senha": senha})
        corpo = _confere_resposta("POST /auth/login", r, auth_actions.login(email, senha), TokenOut,
                                  ignorar=("access_token", "expira_em"))  # token e expiração mudam a cada chamada
        assert corpo["access_token"] and corpo["expira_em"]
        token = corpo["access_token"]
        contexto = auth_actions.exigir_usuario(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
        corpo = _confere_resposta("GET /auth/me", r, {**asdict(contexto), "usuario": contexto.email}, UsuarioOut)
        assert corpo["id"] == uid and corpo["usuario"] == email and corpo["nivel"] == "plataforma"
    finally:
        with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
            conn.execute("DELETE FROM usuario WHERE id = %s", (uid,))


def test_openapi_expoe_os_modelos():
    esquemas = client.get("/openapi.json").json()["components"]["schemas"]
    for nome in ("SaudeOut", "TipoOut", "ResultadoBuscaOut", "LoteCriadoOut", "LoteOut", "ConformidadeEmpresaOut",
                 "ConformidadeLoteOut", "EmpresaResumoOut", "DocumentoOut", "DocumentosAgrupadosOut",
                 "AnalisePontoOut", "ItemFilaRevisaoOut", "RevisaoOut", "EmpresaOut", "TokenOut", "UsuarioOut",
                 "EventoProgressoOut", "ContagensPontoOut"):
        assert nome in esquemas, nome


# ---- varredura: nenhuma rota com response_model fica sem teste de comparação com a action.
# Um campo novo na action que o schema não declare faz o teste da rota falhar (a resposta perde a chave);
# uma rota nova com response_model sem teste faz a varredura abaixo falhar. Os testes citados precisam existir e
# conter o rótulo literal da rota (passado a `_confere`/`_confere_resposta`).
COMPARACOES = {
    "GET /health": ["test_saude_e_tipos"],
    "GET /tipos": ["test_saude_e_tipos"],
    "POST /lotes": ["test_upload_de_lote", "test_reenvio_de_lote_em_erro_devolve_reprocessando"],
    "GET /lotes/{lote_id}": ["test_lote_com_e_sem_eventos", "test_lote_busca_documentos"],
    "GET /busca": ["test_lote_busca_documentos"],
    "GET /documentos": ["test_lote_busca_documentos"],
    "GET /documentos/{documento_id}": ["test_lote_busca_documentos"],
    "PATCH /documentos/{documento_id}/tipo": ["test_revisao_e_correcoes"],
    "PUT /documentos/{documento_id}/campos": ["test_revisao_e_correcoes"],
    "GET /documentos/{documento_id}/analise-ponto": ["test_analise_ponto"],
    "GET /revisao": ["test_revisao_e_correcoes"],
    "POST /documentos/{documento_id}/revisao": ["test_revisao_e_correcoes"],
    "GET /empresas": ["test_conformidade"],
    "GET /empresas/{cnpj:path}/conformidade": ["test_conformidade"],
    "GET /lotes/{lote_id}/conformidade": ["test_conformidade"],
    "POST /cadastro-empresas": ["test_cadastro_empresas"],
    "GET /cadastro-empresas": ["test_cadastro_empresas"],
    "GET /cadastro-empresas/{empresa_id}": ["test_cadastro_empresas"],
    "POST /auth/login": ["test_auth_login_e_me"],
    "GET /auth/me": ["test_auth_login_e_me"],
}


def test_toda_rota_com_response_model_tem_teste_de_comparacao():
    rotas = {f"{m} {c}" for m, c in _rotas_com_modelo()}
    sem_teste = sorted(rotas - set(COMPARACOES))
    assert not sem_teste, f"rotas com response_model sem teste de comparação (acrescente em COMPARACOES): {sem_teste}"
    obsoletas = sorted(set(COMPARACOES) - rotas)
    assert not obsoletas, f"entradas de COMPARACOES sem rota com response_model: {obsoletas}"
    modulo = sys.modules[__name__]
    for rota, testes in COMPARACOES.items():
        for nome in testes:
            teste = getattr(modulo, nome, None)
            assert callable(teste), f"{rota}: teste '{nome}' não existe"
            assert f'"{rota}"' in inspect.getsource(teste), f"{rota}: '{nome}' não compara essa rota com a action"
