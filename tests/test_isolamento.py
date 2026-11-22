"""Isolamento entre organizações: percorre TODAS as rotas da app (enumeradas de `app.routes`) com usuários de cada
nível e confere que ninguém vê, por id, em listagem, busca ou eventos, nada fora do seu escopo; que tomador só lê
(403 em qualquer escrita); e que recurso fora do escopo é 404 idêntico ao inexistente. Rota nova sem classificação
em `EXPLICITAS` (e sem `{lote_id}`/`{documento_id}` no caminho) derruba `test_toda_rota_esta_classificada`.

Contra o Postgres e o Redis reais. O banco é compartilhado: o cenário usa dados próprios (nomes e textos únicos),
as asserções sobre listagens miram o que o cenário criou e, para o restante do banco, comparam com uma regra de
escopo escrita em Python (independente do SQL de app/escopo.py). Cada teste apaga o que criou."""
import json
import time
import uuid

import jwt
import psycopg
import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app import config
from app.api import app
from app.escopo import (
    DEPENDENCIAS_DE_RECURSO, acesso_a_dados, documento_para_escrita, documento_para_leitura, lote_para_escrita,
    lote_para_leitura)
from app.routers.auth.actions import exigir_plataforma, exigir_usuario
from app.routers.lotes import actions as lotes_actions
from conftest import cnpj_valido

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)

INEXISTENTE = 2 ** 62
LEITURA = {"GET", "HEAD", "OPTIONS"}

# ---------- classificação automática das rotas ----------

# /convites/{token} e /convites/{token}/aceitar são públicas de propósito: o token de uso único é a credencial.
ABERTAS = {"/health", "/auth/login", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
           "/convites/{token}", "/convites/{token}/aceitar"}
EXPLICITAS = {  # rotas sem id de lote/documento no caminho, e as que têm mas não seguem a regra geral
    ("GET", "/auth/me"): "qualquer", ("GET", "/tipos"): "qualquer",
    ("GET", "/empresas"): "lista", ("GET", "/empresas/{cnpj:path}/conformidade"): "lista",
    ("POST", "/tomadores"): "plataforma", ("GET", "/tomadores"): "plataforma",
    ("POST", "/prestadores"): "plataforma", ("GET", "/prestadores"): "plataforma",
    ("POST", "/contratos"): "plataforma",
    ("POST", "/empresas-proprias"): "plataforma", ("PUT", "/perfis-jornada/{perfil}"): "plataforma",
    ("PATCH", "/tomadores/{tomador_id}"): "plataforma", ("PATCH", "/prestadores/{prestador_id}"): "plataforma",
    ("PATCH", "/contratos/{contrato_id}"): "plataforma",
    # plataforma ou admin de empresa própria (escopo.leitura_de_perfis / perfil_de_contrato_proprio)
    ("GET", "/perfis-jornada"): "perfil", ("GET", "/perfis-jornada/{perfil}"): "perfil",
    ("PUT", "/contratos/{contrato_id}/perfil-jornada"): "perfil",
    # Autenticadas; a action decide por nível e papel (admin da própria organização), fora do bloqueio de escrita do
    # tomador de propósito: o admin do tomador gerencia terceirizadas e convites (testes em tests/test_terceirizadas.py).
    ("GET", "/convites"): "organizacao", ("GET", "/usuarios"): "organizacao", ("POST", "/terceirizadas"): "organizacao",
    ("PATCH", "/usuarios/{usuario_id}"): "organizacao", ("DELETE", "/convites/{convite_id}"): "organizacao",
    ("POST", "/convites"): "convidar",  # autenticada; quem convida quem é decidido por escopo.pode_convidar
    ("GET", "/contratos"): "lista", ("GET", "/documentos"): "lista", ("GET", "/revisao"): "lista",
    ("GET", "/busca"): "lista", ("GET", "/lotes"): "lista", ("POST", "/lotes"): "upload",
}


def _rotas():
    """(método, caminho, rota) de tudo que a app expõe, incluindo docs e openapi."""
    for rota in app.routes:
        for metodo in sorted(getattr(rota, "methods", None) or ()):
            if metodo not in ("HEAD", "OPTIONS"):
                yield metodo, rota.path, rota


def classificar(metodo: str, caminho: str) -> str:
    if caminho in ABERTAS:
        return "aberta"
    if (metodo, caminho) in EXPLICITAS:
        return EXPLICITAS[(metodo, caminho)]
    if "{lote_id}" in caminho:
        return "lote"
    if "{documento_id}" in caminho:
        return "documento"
    raise AssertionError(f"rota sem classificação em tests/test_isolamento.py: {metodo} {caminho}")


def _chamadas_da_arvore(dependant):
    for sub in dependant.dependencies:
        yield sub.call
        yield from _chamadas_da_arvore(sub)


def _rotas_de_tipo(*tipos, so_escrita=None):
    return [(m, c) for m, c, _ in _rotas() if c not in ABERTAS and classificar(m, c) in tipos
            and (so_escrita is None or (m not in LEITURA) == so_escrita)]


def test_toda_rota_esta_classificada():
    todas = [(m, c) for m, c, _ in _rotas()]
    assert len(todas) >= 25  # está olhando as rotas de verdade
    for m, c in todas:
        classificar(m, c)  # levanta se alguma rota ficou sem cobertura
    inexistentes = [k for k in EXPLICITAS if k not in set(todas)]
    assert not inexistentes, f"EXPLICITAS cita rota que não existe mais: {inexistentes}"
    tipos = {classificar(m, c) for m, c in todas}
    assert {"aberta", "qualquer", "plataforma", "lista", "upload", "lote", "documento", "organizacao", "perfil"} <= tipos


def test_estrutura_das_dependencias_de_cada_rota():
    """Toda rota de dados passa por autenticação e pelo escopo certo (leitura x escrita, lote x documento)."""
    for metodo, caminho, rota in _rotas():
        tipo = classificar(metodo, caminho)
        if tipo == "aberta":
            continue
        assert isinstance(rota, APIRoute), (metodo, caminho)
        chamadas = set(_chamadas_da_arvore(rota.dependant))
        assert exigir_usuario in chamadas, f"{metodo} {caminho} sem autenticação"
        if tipo == "plataforma":
            assert exigir_plataforma in chamadas, f"{metodo} {caminho} deveria ser só da plataforma"
        if tipo == "perfil":  # a dependência de escopo decide; não é só da plataforma nem passa por acesso_a_dados
            assert acesso_a_dados not in chamadas and exigir_plataforma not in chamadas, (metodo, caminho)
        if tipo == "organizacao":  # a action decide por nível e papel; o bloqueio de escrita do tomador não vale aqui
            assert acesso_a_dados not in chamadas and exigir_plataforma not in chamadas, (metodo, caminho)
        if tipo in ("lista", "upload", "lote", "documento"):
            assert acesso_a_dados in chamadas, f"{metodo} {caminho} sem o bloqueio de escrita do tomador"
        if tipo in ("lote", "documento"):
            leitura = metodo in LEITURA
            esperado = {("lote", True): lote_para_leitura, ("lote", False): lote_para_escrita,
                        ("documento", True): documento_para_leitura, ("documento", False): documento_para_escrita}
            assert esperado[(tipo, leitura)] in chamadas, f"{metodo} {caminho} sem verificação de escopo do recurso"
            assert [c for c in chamadas if c in DEPENDENCIAS_DE_RECURSO] == [esperado[(tipo, leitura)]]


# ---------- cenário ----------

NIVEIS = ["plat", "tom1", "tom2", "prest1", "prest2"]
# Lotes por contrato: c11 = (tomador 1, prestador 1), c12 = (t1, p2), c21 = (t2, p1), c22 = (t2, p2, INATIVO).
LOTES = ["c11", "c12", "c21", "c22", "sem"]
ESCOPO = {  # lotes que cada usuário enxerga (decisão de negócio, escrita à mão)
    "plat": {"c11", "c12", "c21", "c22", "sem"},
    "tom1": {"c11", "c12"},  # tomador: histórico inteiro, contrato ativo ou não
    "tom2": {"c21", "c22"},
    "prest1": {"c11", "c21"},
    "prest2": {"c12"},  # c22 está inativo
}
CONTRATOS_VISIVEIS = {"plat": {"c11", "c12", "c21", "c22"}, "tom1": {"c11", "c12"}, "tom2": {"c21", "c22"},
                      "prest1": {"c11", "c21"}, "prest2": {"c12"}}


class Cenario:
    pass


def _montar(conn) -> Cenario:
    c = Cenario()
    c.token = f"isol{uuid.uuid4().hex}"  # palavra única nas páginas, para a busca
    c.tomador = {n: conn.execute("INSERT INTO tomador (nome) VALUES (%s) RETURNING id",
                                 (f"Tomador {n} {uuid.uuid4().hex}",)).fetchone()[0] for n in (1, 2)}
    c.prestador = {n: conn.execute("INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING id",
                                   (cnpj_valido(uuid.uuid4().int), f"Prestador {n} {uuid.uuid4().hex}")
                                   ).fetchone()[0] for n in (1, 2)}
    pares = {"c11": (1, 1, True), "c12": (1, 2, True), "c21": (2, 1, True), "c22": (2, 2, False)}
    c.contrato = {nome: conn.execute(
        "INSERT INTO contrato (tomador_id, prestador_id, ativo) VALUES (%s, %s, %s) RETURNING id",
        (c.tomador[t], c.prestador[p], ativo)).fetchone()[0] for nome, (t, p, ativo) in pares.items()}
    c.usuario = {}
    for nome in NIVEIS:
        nivel = "plataforma" if nome == "plat" else "tomador" if nome.startswith("tom") else "prestador"
        tom = c.tomador[int(nome[-1])] if nivel == "tomador" else None
        pre = c.prestador[int(nome[-1])] if nivel == "prestador" else None
        c.usuario[nome] = conn.execute(
            "INSERT INTO usuario (email, nome, nivel, papel, tomador_id, prestador_id) "
            "VALUES (%s, %s, %s, 'admin', %s, %s) RETURNING id",
            (f"{nome}-{uuid.uuid4().hex}@exemplo.invalid", f"Usuário {nome}", nivel, tom, pre)).fetchone()[0]
    c.lote, c.doc = {}, {}
    for nome in LOTES:
        lote = conn.execute(
            "INSERT INTO lote (sha256, nome_arquivo, estado, contrato_id) VALUES (%s, %s, 'recebido', %s) RETURNING id",
            (uuid.uuid4().hex + uuid.uuid4().hex, f"{nome}.pdf", c.contrato.get(nome))).fetchone()[0]
        doc = conn.execute(
            "INSERT INTO documento (lote_id, ordem, pagina_ini, pagina_fim, estado, tipo, confianca) "
            "VALUES (%s, 1, 1, 1, 'em_revisao', 'aso', 0.5) RETURNING id", (lote,)).fetchone()[0]
        conn.execute("INSERT INTO pagina (lote_id, numero, documento_id, texto) VALUES (%s, 1, %s, %s)",
                     (lote, doc, f"{c.token} documento do lote {nome}"))
        c.lote[nome], c.doc[nome] = lote, doc
    return c


def _apagar(conn, c: Cenario) -> None:
    conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (list(c.lote.values()),))
    conn.execute("DELETE FROM usuario WHERE id = ANY(%s)", (list(c.usuario.values()),))
    conn.execute("DELETE FROM contrato WHERE id = ANY(%s)", (list(c.contrato.values()),))
    conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (list(c.prestador.values()),))
    conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (list(c.tomador.values()),))


@pytest.fixture
def cen():
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    c = _montar(conn)
    c.db = conn
    try:
        yield c
    finally:
        _apagar(conn, c)
        conn.close()


def _h(cen: Cenario, nome: str) -> dict:
    """Cabeçalho com um token de verdade (o nível e o vínculo valem os do banco)."""
    return _h_id(cen.usuario[nome])


def _h_id(uid: int) -> dict:
    agora = int(time.time())
    return {"Authorization": "Bearer " + jwt.encode(
        {"sub": str(uid), "iat": agora - 5, "exp": agora + 600}, config.AUTH_SEGREDO, algorithm="HS256")}


def _req(metodo, caminho, headers, **kw):
    return client.request(metodo, caminho, headers=headers, **kw)


def _caminho(modelo: str, lote=None, doc=None) -> str:
    caminho = modelo.replace("{lote_id}", str(lote)).replace("{documento_id}", str(doc)).replace("{numero}", "1")
    return caminho + ("?once=true" if caminho.endswith("/eventos") else "")


def _corpo(metodo, caminho) -> dict:
    if metodo == "PATCH":
        return {"json": {"tipo": "aso", "revisor": "revisor-teste"}}
    if metodo == "PUT":
        return {"json": {"campos": {"nome": "Fulano"}, "revisor": "revisor-teste"}}
    if metodo == "POST" and caminho.endswith("/revisao"):
        return {"json": {"tipo": "aso", "revisor": "revisor-teste"}}
    return {}


DETALHES_DE_ESCOPO = ("lote não encontrado", "documento não encontrado")


def _barrado_por_escopo(resp) -> bool:
    return resp.status_code == 404 and resp.json().get("detail") in DETALHES_DE_ESCOPO


# ---------- leitura por id ----------

@pytest.mark.parametrize("nome", NIVEIS)
@pytest.mark.parametrize("metodo,modelo", _rotas_de_tipo("lote", "documento", so_escrita=False))
def test_leitura_por_id_so_dentro_do_escopo(cen, nome, metodo, modelo):
    h = _h(cen, nome)
    inexistente = _req(metodo, _caminho(modelo, INEXISTENTE, INEXISTENTE), h)
    assert inexistente.status_code == 404
    for lote in LOTES:
        resp = _req(metodo, _caminho(modelo, cen.lote[lote], cen.doc[lote]), h)
        if lote in ESCOPO[nome]:
            assert not _barrado_por_escopo(resp), (nome, lote, metodo, modelo, resp.status_code, resp.text[:200])
            assert resp.status_code != 403, (nome, lote, metodo, modelo)
        else:  # não revela existência: igual ao inexistente
            assert resp.status_code == 404 and resp.json() == inexistente.json(), (nome, lote, metodo, modelo)
            assert cen.token not in resp.text


@pytest.mark.parametrize("nome", NIVEIS)
def test_leitura_dentro_do_escopo_devolve_so_o_proprio_recurso(cen, nome):
    h = _h(cen, nome)
    for lote in ESCOPO[nome]:
        corpo = _req("GET", f"/lotes/{cen.lote[lote]}", h).json()
        assert corpo["id"] == cen.lote[lote] and [d["id"] for d in corpo["documentos"]] == [cen.doc[lote]]
        doc = _req("GET", f"/documentos/{cen.doc[lote]}", h).json()
        assert doc["lote_id"] == cen.lote[lote]
        assert all(cen.token in p["texto"] and lote in p["texto"] for p in doc["paginas"])


@pytest.mark.parametrize("nome", NIVEIS)
def test_eventos_sse_so_do_lote_no_escopo(cen, nome):
    h = _h(cen, nome)
    for lote in LOTES:
        resp = _req("GET", f"/lotes/{cen.lote[lote]}/eventos?once=true", h)
        if lote in ESCOPO[nome]:
            assert resp.status_code == 200 and resp.headers["content-type"].startswith("text/event-stream")
            quadros = [json.loads(q[len("data: "):]) for q in resp.text.split("\n\n") if q.startswith("data: ")]
            assert quadros and {q["id"] for q in quadros} == {cen.lote[lote]}
            assert all(d["id"] == cen.doc[lote] for q in quadros for d in q["documentos"])
        else:
            assert resp.status_code == 404 and "data:" not in resp.text


# ---------- escrita por id ----------

def _escritas():
    return _rotas_de_tipo("lote", "documento", so_escrita=True)


@pytest.mark.parametrize("nome", NIVEIS)
@pytest.mark.parametrize("metodo,modelo", [r for r in _escritas() if r not in EXPLICITAS])
def test_escrita_por_id(cen, nome, metodo, modelo):
    """Tomador: 403 sempre (dentro ou fora do escopo). Prestador: passa só nos lotes dele, o resto é 404 igual ao
    inexistente. Plataforma: passa em tudo. Cenário novo por teste: as escritas mudam o estado."""
    h = _h(cen, nome)
    inexistente = _req(metodo, _caminho(modelo, INEXISTENTE, INEXISTENTE), h, **_corpo(metodo, modelo))
    for lote in LOTES:
        antes = cen.db.execute("SELECT estado FROM documento WHERE id = %s", (cen.doc[lote],)).fetchone()
        resp = _req(metodo, _caminho(modelo, cen.lote[lote], cen.doc[lote]), h, **_corpo(metodo, modelo))
        depois = cen.db.execute("SELECT estado FROM documento WHERE id = %s", (cen.doc[lote],)).fetchone()
        if nome.startswith("tom"):
            assert resp.status_code == inexistente.status_code == 403, (nome, lote, metodo, modelo)
            assert depois == antes, "tomador alterou dados"
        elif lote in ESCOPO[nome]:
            assert resp.status_code not in (401, 403) and not _barrado_por_escopo(resp), \
                (nome, lote, metodo, modelo, resp.status_code, resp.text[:200])
        else:
            assert resp.status_code == 404 and resp.json() == inexistente.json(), (nome, lote, metodo, modelo)
            assert depois == antes, "escrita fora do escopo alterou dados"


# ---------- listagens e busca ----------

def _permitidos(conn, nome: str, cen: Cenario) -> tuple[set[int], set[int]]:
    """(lotes, contratos) do usuário em todo o banco, pela regra escrita em Python (não pelo SQL do app)."""
    uid = cen.usuario[nome]
    nivel, tom, pre = conn.execute("SELECT nivel, tomador_id, prestador_id FROM usuario WHERE id = %s",
                                   (uid,)).fetchone()
    contratos = set()
    for cid, c_ativo, t_id, p_id, t_ativo, p_ativo in conn.execute(
            "SELECT c.id, c.ativo, c.tomador_id, c.prestador_id, t.ativo, p.ativo FROM contrato c "
            "JOIN tomador t ON t.id = c.tomador_id JOIN prestador p ON p.id = c.prestador_id"):
        if nivel == "plataforma" or (nivel == "tomador" and t_id == tom and t_ativo) or (
                nivel == "prestador" and p_id == pre and c_ativo and t_ativo and p_ativo):
            contratos.add(cid)
    lotes = {l for (l, k) in conn.execute("SELECT id, contrato_id FROM lote")
             if (nivel == "plataforma") or (k is not None and k in contratos)}
    return lotes, contratos


def _da_cena(cen, nomes):
    return {cen.lote[n] for n in nomes}


def _docs_de_documentos(corpo) -> list[dict]:
    return [d for g in corpo["grupos"] for d in g["documentos"]]


@pytest.mark.parametrize("nome", NIVEIS)
def test_listagens_e_busca_filtram_no_escopo(cen, nome):
    h = _h(cen, nome)
    lotes_ok, contratos_ok = _permitidos(cen.db, nome, cen)
    esperados = _da_cena(cen, ESCOPO[nome])
    todos = set(cen.lote.values())

    docs = _req("GET", "/documentos", h)
    assert docs.status_code == 200
    vistos = {d["lote_id"] for d in _docs_de_documentos(docs.json())}
    assert vistos & todos == esperados
    if nome != "plat":
        assert vistos <= lotes_ok

    fila = _req("GET", "/revisao", h)
    assert fila.status_code == 200
    vistos = {i["lote_id"] for i in fila.json()}
    assert vistos & todos == esperados
    if nome != "plat":
        assert vistos <= lotes_ok

    busca = _req("GET", "/busca", h, params={"q": cen.token, "limite": 100})
    assert busca.status_code == 200
    vistos = {i["lote_id"] for i in busca.json()}
    assert vistos & todos == esperados and vistos <= (lotes_ok if nome != "plat" else vistos)
    assert all(i["documento_id"] in cen.doc.values() for i in busca.json() if i["lote_id"] in todos)
    if nome != "plat":
        assert vistos == esperados, "busca devolveu algo além do que o cenário permite"

    contratos = _req("GET", "/contratos", h)
    assert contratos.status_code == 200
    ids = {c["id"] for c in contratos.json()}
    assert ids <= contratos_ok or nome == "plat"
    assert ids & set(cen.contrato.values()) == {cen.contrato[n] for n in CONTRATOS_VISIVEIS[nome]}
    # filtros do próprio chamador não furam o escopo
    outro = _req("GET", "/contratos", h, params={"tomador_id": cen.tomador[2], "prestador_id": cen.prestador[2]})
    assert {c["id"] for c in outro.json()} & set(cen.contrato.values()) == (
        {cen.contrato["c22"]} if "c22" in CONTRATOS_VISIVEIS[nome] else set())


@pytest.mark.parametrize("nome", NIVEIS)
def test_documentos_por_contrato_fora_do_escopo_e_404_igual_ao_inexistente(cen, nome):
    h = _h(cen, nome)
    inexistente = _req("GET", "/documentos", h, params={"contrato_id": INEXISTENTE})
    assert inexistente.status_code == 404
    for contrato in ("c11", "c12", "c21", "c22"):
        resp = _req("GET", "/documentos", h, params={"contrato_id": cen.contrato[contrato]})
        if contrato in CONTRATOS_VISIVEIS[nome]:
            assert resp.status_code == 200
            assert {d["lote_id"] for d in _docs_de_documentos(resp.json())} == {cen.lote[contrato]}
        else:
            assert resp.status_code == 404 and resp.json() == inexistente.json()


def test_busca_nao_acha_texto_de_outra_organizacao_nem_pelo_trecho(cen):
    h = _h(cen, "prest2")
    corpo = _req("GET", "/busca", h, params={"q": cen.token}).json()
    assert [i["lote_id"] for i in corpo] == [cen.lote["c12"]]
    assert "lote c11" not in json.dumps(corpo) and "lote sem" not in json.dumps(corpo)


# ---------- upload ----------

@pytest.fixture
def envio(monkeypatch):
    enfileirados = []
    monkeypatch.setattr(lotes_actions, "enfileirar", lambda r, fila, payload, *a, **k: enfileirados.append(payload))
    criados = []

    def enviar(headers, contrato_id=None):
        form = {} if contrato_id is None else {"contrato_id": str(contrato_id)}
        r = client.post("/lotes", headers=headers, data=form,
                        files={"arquivo": ("a.pdf", b"%PDF-1.4 isolamento " + uuid.uuid4().hex.encode(),
                                           "application/pdf")})
        if r.status_code == 200:
            criados.append(r.json()["lote_id"])
        return r
    yield enviar, enfileirados
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM lote WHERE id = ANY(%s)", (criados,))


def test_upload_tomador_recebe_403_em_qualquer_contrato(cen, envio):
    enviar, jobs = envio
    for contrato in (None, cen.contrato["c11"], cen.contrato["c21"], INEXISTENTE):
        assert enviar(_h(cen, "tom1"), contrato).status_code == 403
    assert jobs == []


def test_upload_prestador_exige_contrato_dele_ativo(cen, envio):
    enviar, jobs = envio
    h = _h(cen, "prest1")
    assert enviar(h).status_code == 422  # contrato ausente
    inexistente = enviar(h, INEXISTENTE)
    assert inexistente.status_code == 404
    for fora in ("c12", "c22"):  # de outro prestador
        r = enviar(h, cen.contrato[fora])
        assert r.status_code == 404 and r.json()["detail"].split()[0] == inexistente.json()["detail"].split()[0]
    assert jobs == []
    ok = enviar(h, cen.contrato["c11"])
    assert ok.status_code == 200 and ok.json()["contrato_id"] == cen.contrato["c11"]
    assert cen.db.execute("SELECT contrato_id FROM lote WHERE id = %s", (ok.json()["lote_id"],)).fetchone()[0] \
        == cen.contrato["c11"]
    assert len(jobs) == 1
    # contrato dele, mas inativo: fora do escopo (404, não 409)
    assert enviar(_h(cen, "prest2"), cen.contrato["c22"]).status_code == 404
    assert enviar(_h(cen, "prest2"), cen.contrato["c12"]).status_code == 200


def test_upload_plataforma_com_e_sem_contrato(cen, envio):
    enviar, _ = envio
    assert enviar(_h(cen, "plat")).status_code == 200  # lote sem contrato: só a plataforma envia
    assert enviar(_h(cen, "plat"), cen.contrato["c11"]).status_code == 200
    assert enviar(_h(cen, "plat"), cen.contrato["c22"]).status_code == 409  # inativo


def test_lote_enviado_pelo_prestador_fica_invisivel_aos_outros(cen, envio):
    enviar, _ = envio
    lote = enviar(_h(cen, "prest1"), cen.contrato["c11"]).json()["lote_id"]
    assert client.get(f"/lotes/{lote}", headers=_h(cen, "tom1")).status_code == 200
    for nome in ("tom2", "prest2"):
        assert client.get(f"/lotes/{lote}", headers=_h(cen, nome)).status_code == 404


# ---------- inatividade ----------

def test_contrato_inativo_some_para_prestador_e_fica_no_historico_do_tomador(cen):
    cen.db.execute("UPDATE contrato SET ativo = false WHERE id = %s", (cen.contrato["c11"],))
    lote = cen.lote["c11"]
    assert client.get(f"/lotes/{lote}", headers=_h(cen, "prest1")).status_code == 404
    assert client.get(f"/documentos/{cen.doc['c11']}", headers=_h(cen, "prest1")).status_code == 404
    assert client.post(f"/lotes/{lote}/cancelar", headers=_h(cen, "prest1")).status_code == 404
    assert client.get(f"/lotes/{lote}", headers=_h(cen, "tom1")).status_code == 200
    ids = {c["id"] for c in client.get("/contratos", headers=_h(cen, "prest1")).json()}
    assert cen.contrato["c11"] not in ids
    ids = {c["id"] for c in client.get("/contratos", headers=_h(cen, "tom1")).json()}
    assert cen.contrato["c11"] in ids


def test_tomador_inativo_derruba_o_acesso_do_prestador_ao_contrato(cen):
    cen.db.execute("UPDATE tomador SET ativo = false WHERE id = %s", (cen.tomador[1],))
    assert client.get(f"/lotes/{cen.lote['c11']}", headers=_h(cen, "prest1")).status_code == 404
    assert client.get(f"/lotes/{cen.lote['c21']}", headers=_h(cen, "prest1")).status_code == 200
    assert client.get("/tipos", headers=_h(cen, "tom1")).status_code == 401  # o próprio tomador inativo perde o login


def test_usuario_inativo_nao_acessa_nada(cen):
    cen.db.execute("UPDATE usuario SET ativo = false WHERE id = %s", (cen.usuario["prest1"],))
    h = _h(cen, "prest1")
    for caminho in ("/tipos", "/contratos", "/documentos", "/revisao", f"/lotes/{cen.lote['c11']}"):
        assert client.get(caminho, headers=h).status_code == 401


# ---------- rotas só da plataforma, de qualquer usuário e abertas ----------

@pytest.mark.parametrize("nome", NIVEIS)
@pytest.mark.parametrize("metodo,modelo", [(m, c) for m, c, _ in _rotas()
                                           if c not in ABERTAS and classificar(m, c) in ("plataforma", "perfil")])
def test_rotas_so_da_plataforma(cen, nome, metodo, modelo):
    """Inclui as rotas de perfil (plataforma ou admin de empresa própria): ninguém do cenário tem contrato próprio."""
    caminho = _caminho(modelo, cen.lote["c11"], cen.doc["c11"]).replace("{cnpj:path}", cnpj_valido(1))
    resp = _req(metodo, caminho, _h(cen, nome))
    if nome == "plat":
        assert resp.status_code != 403
    else:
        assert resp.status_code == 403, (nome, metodo, modelo, resp.status_code)


@pytest.mark.parametrize("nome", NIVEIS)
@pytest.mark.parametrize("metodo,modelo", [(m, c) for m, c, _ in _rotas()
                                           if c not in ABERTAS and classificar(m, c) == "qualquer"])
def test_rotas_de_qualquer_usuario_logado(cen, nome, metodo, modelo):
    assert _req(metodo, modelo, _h(cen, nome)).status_code == 200
    assert _req(metodo, modelo, None).status_code == 401


def test_sem_token_toda_rota_nao_aberta_da_401(cen):
    for metodo, modelo, _ in _rotas():
        if modelo in ABERTAS:
            continue
        resp = _req(metodo, _caminho(modelo, cen.lote["c11"], cen.doc["c11"]).replace("{cnpj:path}", cnpj_valido(1)),
                    None)
        assert resp.status_code == 401, (metodo, modelo, resp.status_code)
