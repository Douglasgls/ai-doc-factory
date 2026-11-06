"""Anonimização na saída para LLM (corpo capturado em llm._enviar) e nas respostas da API (Postgres do compose).
Nenhum teste usa a rede."""
import json
import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from app import analise, classificador_llm, config, llm, prompts, segmentacao
from app.api import app
from app.campos import gravar_campo

client = TestClient(app)
CPF, CPF_PLANO = "529.982.247-25", "52998224725"
CPF2 = "111.444.777-35"
NOME = "Mariana Quintanilha Albuquerque"
CNPJ = "11222333000181"
TEXTO = (f"EMPRESA TESTE LTDA\nCNPJ 11.222.333/0001-81\nRECIBO DE PAGAMENTO DE SALÁRIO\n{NOME}\n"
         f"CPF {CPF}\nNascimento: 01/02/1990\n07:30 - 11:30 / 12:30 - 16:30\n")


def _vazou(corpo) -> bool:
    s = json.dumps(corpo, ensure_ascii=False)
    return any(x in s for x in (CPF, CPF_PLANO, "529.982", "Quintanilha", "01/02/1990"))


@pytest.fixture
def capturar(monkeypatch):
    """Substitui llm._enviar: guarda o corpo e devolve a próxima resposta da fila."""
    estado = {"corpos": [], "respostas": []}

    def enviar(url, headers, corpo):
        estado["corpos"].append(corpo)
        item = estado["respostas"].pop(0) if estado["respostas"] else httpx.Response(400, json={})
        return item
    monkeypatch.setattr(llm, "_enviar", enviar)
    return estado


# ---------- saída para LLM ----------

def test_classificacao_nao_envia_cpf_nem_nome_ao_jev(capturar):
    probs = {t: 0.01 for t in (*config.TIPOS, prompts.NENHUM)}
    capturar["respostas"].append(httpx.Response(200, json={
        "model": "jev-x", "answers": {"tipo": {"type": "choice", "choice": "holerite", "confidence": 0.97,
                                               "probabilities": probs}}}))
    r = classificador_llm._jev(TEXTO)
    assert r.tipo == "holerite"
    (corpo,) = capturar["corpos"]
    assert not _vazou(corpo)
    texto_enviado = corpo["state"]["documento"]["texto"]
    assert "[CPF]" in texto_enviado and "[NOME]" in texto_enviado and "[NASCIMENTO]" in texto_enviado
    assert "RECIBO DE PAGAMENTO DE SALÁRIO" in texto_enviado  # o que o classificador precisa ler
    assert "CNPJ 11.222.333/0001-81" in texto_enviado and "07:30 - 11:30" in texto_enviado


def test_fronteira_nao_envia_cpf_nem_nome_ao_jev(capturar, monkeypatch):
    monkeypatch.setattr(config, "CLASSIFICADOR", "jev")
    capturar["respostas"].append(httpx.Response(200, json={"answers": {"q": {"noul": 0.9}}}))
    assert segmentacao.perguntar_llm_mesmo_documento(f"... {NOME}\nCPF {CPF}", f"{NOME}\nCPF {CPF_PLANO} página 2") is True
    (corpo,) = capturar["corpos"]
    assert not _vazou(corpo)
    assert "[CPF]" in json.dumps(corpo)


def test_analise_ponto_nao_envia_cpf_nem_nome_ao_gemini_nem_ao_jev(capturar):
    capturar["respostas"].append(httpx.Response(200, json={}))  # o Gemini falha depois de capturar o corpo
    with pytest.raises(llm.LLMErro):
        analise.extrair_com_gemini(TEXTO, [], {"jornada_diaria_min": 480})
    (corpo,) = capturar["corpos"]
    prompt = corpo["contents"][0]["parts"][0]["text"]
    assert not _vazou(corpo)
    assert "07:30 - 11:30 / 12:30 - 16:30" in prompt and "[NOME]" in prompt  # marcações intactas

    capturar["respostas"].append(httpx.Response(400, json={}))
    with pytest.raises(llm.LLMErro):
        analise.julgar_com_jev({"horas_extras": 1}, f"Folha de {NOME}, CPF {CPF}: horas extras")
    assert not _vazou(capturar["corpos"][1])
    assert "horas extras" in json.dumps(capturar["corpos"][1], ensure_ascii=False)


# ---------- respostas da API ----------

@pytest.fixture
def lote_pessoas():
    """Dois documentos de uma empresa, mesmo CPF e nomes diferentes; um terceiro em revisão."""
    criados = []

    def criar(docs, texto=TEXTO):
        """docs: [(tipo, estado, campos)]. Devolve (lote_id, [ids])."""
        with psycopg.connect(config.DATABASE_URL) as conn:
            lote = conn.execute("INSERT INTO lote (sha256, nome_arquivo, estado) VALUES (%s, 't.pdf', 'concluido') "
                                "RETURNING id", (uuid.uuid4().hex + uuid.uuid4().hex,)).fetchone()[0]
            ids = []
            for n, (t, e, campos) in enumerate(docs, start=1):
                i = conn.execute("INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, tipo, estado) "
                                 "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id", (lote, n, n, n, t, e)).fetchone()[0]
                conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, %s, %s, %s)",
                             (lote, n, i, texto))
                for k, v in campos.items():
                    gravar_campo(conn, i, k, v, "teste")
                ids.append(i)
        criados.append(lote)
        return lote, ids
    yield criar
    with psycopg.connect(config.DATABASE_URL) as conn:
        for lote in criados:
            conn.execute("DELETE FROM lote WHERE id = %s", (lote,))


def _campos(cpf=CPF_PLANO, nome=NOME, **extra):
    return {"cnpj_prestadora": CNPJ, "razao_social_prestadora": "Empresa Teste Ltda", "distingue_prestadora": "true",
            "nome": nome, "cpf": cpf, **extra}


def _db_campos(doc_id):
    with psycopg.connect(config.DATABASE_URL) as conn:
        return dict(conn.execute("SELECT campo, valor FROM documento_campos WHERE documento_id = %s", (doc_id,)))


def test_documento_mascara_texto_e_campos_mas_mantem_nome(lote_pessoas):
    _, (d,) = lote_pessoas([("holerite", "classificado", _campos(rg="12.345.678-9", pis="123.45678.90-1"))])
    j = client.get(f"/documentos/{d}").json()
    assert CPF not in json.dumps(j) and CPF_PLANO not in json.dumps(j) and "12.345.678" not in json.dumps(j)
    assert "***.982.247-**" in j["paginas"][0]["texto"] and NOME in j["paginas"][0]["texto"]
    assert j["campos"]["cpf"] == "***.982.247-**" and j["campos"]["rg"] == "***"
    assert j["campos"]["pis"] == "***" and j["campos"]["nome"] == NOME and j["pessoa"] == NOME
    assert _db_campos(d)["cpf"] == CPF_PLANO  # o banco guarda o valor real


def test_listagens_mascaram_cpf(lote_pessoas):
    _, (a, b) = lote_pessoas([("holerite", "classificado", _campos()), ("holerite", "em_revisao", _campos())])
    docs = [x for g in client.get("/documentos").json()["grupos"] for x in g["documentos"] if x["id"] in (a, b)]
    assert len(docs) == 2 and all(x["campos"]["cpf"] == "***.982.247-**" and x["pessoa"] == NOME for x in docs)
    fila = [x for x in client.get("/revisao").json() if x["id"] == b]
    assert len(fila) == 1 and fila[0]["campos"]["cpf"] == "***.982.247-**" and CPF_PLANO not in json.dumps(fila)


def test_busca_acha_por_cpf_e_por_nome_sem_revelar_o_cpf(lote_pessoas):
    lote, (d,) = lote_pessoas([("holerite", "classificado", _campos())])
    # (CPF só com dígitos não casa com o texto pontuado no FTS; isso já era assim antes da anonimização)
    for q in (CPF, "Quintanilha"):
        achados = [x for x in client.get("/busca", params={"q": q, "limite": 100}).json() if x["lote_id"] == lote]
        assert len(achados) == 1 and achados[0]["documento_id"] == d, q
        assert CPF not in achados[0]["trecho"] and CPF_PLANO not in achados[0]["trecho"], q
    trecho = [x for x in client.get("/busca", params={"q": "Quintanilha"}).json() if x["lote_id"] == lote][0]["trecho"]
    assert "<b>Quintanilha</b>" in trecho  # as tags continuam
    assert "***.982.247-**" in trecho


def test_put_campos_com_cpf_mascarado_e_rejeitado_e_nao_destroi_o_valor(lote_pessoas):
    _, (d,) = lote_pessoas([("holerite", "classificado", _campos(rg="12.345.678-9"))])
    r = client.put(f"/documentos/{d}/campos", json={"campos": {"cpf": "***.982.247-**", "nome": "Outro"}, "revisor": "ana"})
    assert r.status_code == 422 and "mascarado" in r.text
    r = client.put(f"/documentos/{d}/campos", json={"campos": {"rg": "***"}, "revisor": "ana"})
    assert r.status_code == 422
    db = _db_campos(d)
    assert db["cpf"] == CPF_PLANO and db["rg"] == "12.345.678-9" and db["nome"] == NOME  # nada foi gravado

    # omitir o campo mascarado mantém o real; a resposta continua mascarada
    r = client.put(f"/documentos/{d}/campos", json={"campos": {"nome": "Outro Nome"}, "revisor": "ana"})
    assert r.status_code == 200 and r.json()["campos"]["nome"] == "Outro Nome"
    assert r.json()["campos"]["cpf"] == "***.982.247-**" and CPF_PLANO not in r.text
    assert _db_campos(d)["cpf"] == CPF_PLANO

    # valor completo novo substitui o real
    r = client.put(f"/documentos/{d}/campos", json={"campos": {"cpf": CPF2}, "revisor": "ana"})
    assert r.status_code == 200 and r.json()["campos"]["cpf"] == "***.444.777-**"
    assert _db_campos(d)["cpf"] == CPF2


def test_patch_tipo_responde_com_campos_mascarados(lote_pessoas):
    _, (d,) = lote_pessoas([("holerite", "em_revisao", _campos())])
    r = client.patch(f"/documentos/{d}/tipo", json={"tipo": "aso", "revisor": "ana"})
    assert r.status_code == 200 and CPF_PLANO not in r.text and CPF not in r.text
    assert r.json()["campos"]["cpf"] == "***.982.247-**"


def test_conformidade_mascara_cpf_mas_detecta_divergencia_de_nome_do_mesmo_cpf(lote_pessoas):
    lote, (a, b, c) = lote_pessoas([
        ("holerite", "classificado", _campos(nome="Maria Silva")),
        ("folha_ponto", "classificado", _campos(nome="Mario Silva")),         # mesmo CPF, nome diferente
        ("holerite", "classificado", _campos(cpf=CPF2.replace(".", "").replace("-", ""), nome="João Souza")),
    ])
    j = client.get(f"/empresas/{CNPJ}/conformidade")
    assert j.status_code == 200
    for cru in (CPF, CPF_PLANO, CPF2, "52998224725", "11144477735"):
        assert cru not in j.text
    div = [d for d in j.json()["geral"]["descontos"] if d["regra"] == "campo_divergente"]
    assert len(div) == 1 and div[0]["campo"] == "nome" and div[0]["cpf"] == "***.982.247-**"
    assert {v["valor"] for v in div[0]["valores"]} == {"Maria Silva", "Mario Silva"}  # João (outro CPF) não entra

    for url in ("/empresas", f"/lotes/{lote}/conformidade"):
        r = client.get(url)
        assert r.status_code == 200 and CPF_PLANO not in r.text and "11144477735" not in r.text


def test_analise_ponto_mascara_cpf_em_texto_livre(lote_pessoas):
    _, (d,) = lote_pessoas([("folha_ponto", "classificado", {})])
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        analise._gravar(conn, d, "concluida", {
            "analise": f"Folha de {NOME}, CPF {CPF}.", "divergencias": [{"tipo": "x", "evidencia": f"cpf {CPF_PLANO}"}]})
    r = client.get(f"/documentos/{d}/analise-ponto")
    assert r.status_code == 200 and CPF not in r.text and CPF_PLANO not in r.text and "***.982.247-**" in r.text
