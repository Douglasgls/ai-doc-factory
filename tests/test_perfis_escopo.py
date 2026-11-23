"""Escopo dos perfis de jornada: cada perfil (exceto o Padrão) é geral ou de um prestador. Plataforma vê e edita tudo;
admin de empresa própria vê o Padrão, os gerais e os dele, cria perfis dele e edita só esses. Fora do escopo = 404 (o
mesmo corpo de um perfil inexistente); visível mas de outro dono = 403. Contra o Postgres real; só valores falsos."""
import re
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import analise, config
from app.api import app
from app.ponto import PERFIL_PADRAO, carregar_perfil
from test_analise import IRREGULAR, _doc, _gemini, _jev, rede  # noqa: F401  (rede é fixture)
from test_empresa_propria import _admin, criar  # noqa: F401  (criar é fixture)
from test_terceirizadas import _h_id, mundo  # noqa: F401  (mundo é fixture)

pytestmark = pytest.mark.usefixtures("auth_real")
client = TestClient(app)
PARAMETROS = {"parametros": [{"parametro": "extras_max_dia_min", "valor": 90, "base_legal": "acordo de teste"}]}


@pytest.fixture
def slugs():
    """Slugs criados no teste (por POST ou direto no banco); cadastro e parâmetros saem no fim."""
    criados = []
    yield criados
    with psycopg.connect(config.DATABASE_URL, autocommit=True) as conn:
        conn.execute("DELETE FROM perfil_jornada_cadastro WHERE perfil = ANY(%s)", (criados,))
        conn.execute("DELETE FROM perfil_jornada WHERE perfil = ANY(%s)", (criados,))


class Cena:
    pass


@pytest.fixture
def cena(mundo, criar, slugs):
    """Duas empresas próprias (X e Y) e perfis: G geral, OX de X, OY de Y, L "não geral e sem dono" (como os que
    existiam antes do escopo)."""
    c = Cena()
    c.mundo, c.slugs, c.plat = mundo, slugs, criar.plat
    c.x, c.y = criar(), criar()
    c.hx, c.hy = _admin(mundo, c.x), _admin(mundo, c.y)
    c.px, c.py = c.x.json()["prestador"]["id"], c.y.json()["prestador"]["id"]
    c.cx, c.cy = c.x.json()["contrato"]["id"], c.y.json()["contrato"]["id"]

    def novo(nome, **extra):
        r = client.post("/perfis-jornada", headers=c.plat, json={"nome": nome, **extra})
        assert r.status_code == 201, r.text
        slugs.append(r.json()["perfil"])
        return r.json()["perfil"]
    c.G = novo("Geral", geral=True)
    c.OX = novo("Dono X", prestador_id=c.px)
    c.OY = novo("Dono Y", prestador_id=c.py)
    c.L = "legado_" + uuid.uuid4().hex[:8]
    slugs.append(c.L)
    mundo.db.execute("INSERT INTO perfil_jornada_cadastro (perfil, nome) VALUES (%s, 'Legado')", (c.L,))
    mundo.db.execute("INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) "
                     "VALUES (%s, 'extras_max_dia_min', 30, 'min', 'x')", (c.L,))
    return c


def _lista(headers):
    r = client.get("/perfis-jornada", headers=headers)
    assert r.status_code == 200, r.text
    return {p["perfil"]: p for p in r.json()}


def test_plataforma_ve_tudo(cena):
    lista = _lista(cena.plat)
    assert {PERFIL_PADRAO, cena.G, cena.OX, cena.OY, cena.L} <= set(lista)
    assert (lista[cena.G]["geral"], lista[cena.G]["prestador_id"]) == (True, None)
    assert (lista[cena.OX]["geral"], lista[cena.OX]["prestador_id"]) == (False, cena.px)
    assert (lista[cena.L]["geral"], lista[cena.L]["prestador_id"]) == (False, None)
    assert all(p["editavel"] for p in lista.values() if p["perfil"] != PERFIL_PADRAO)
    assert lista[PERFIL_PADRAO]["editavel"] is False
    for slug in (cena.G, cena.OX, cena.OY, cena.L):
        assert client.get(f"/perfis-jornada/{slug}", headers=cena.plat).status_code == 200


def test_dois_admins_nao_se_veem_e_o_geral_aparece_para_os_dois(cena):
    lx, ly = _lista(cena.hx), _lista(cena.hy)
    visiveis_x = {p for p in lx if p in {PERFIL_PADRAO, cena.G, cena.OX, cena.OY, cena.L}}
    visiveis_y = {p for p in ly if p in {PERFIL_PADRAO, cena.G, cena.OX, cena.OY, cena.L}}
    assert visiveis_x == {PERFIL_PADRAO, cena.G, cena.OX}
    assert visiveis_y == {PERFIL_PADRAO, cena.G, cena.OY}
    assert (lx[cena.OX]["editavel"], lx[cena.G]["editavel"], lx[PERFIL_PADRAO]["editavel"]) == (True, False, False)
    assert lx[cena.OX]["prestador_id"] == cena.px and lx[cena.G]["prestador_id"] is None
    inexistente = client.get("/perfis-jornada/nao_existe_de_jeito_nenhum", headers=cena.hx)
    assert inexistente.status_code == 404
    for h, fora in ((cena.hx, (cena.OY, cena.L)), (cena.hy, (cena.OX, cena.L))):
        for slug in fora:  # o mesmo corpo de um perfil inexistente (trocando só o nome)
            r = client.get(f"/perfis-jornada/{slug}", headers=h)
            assert r.status_code == 404 and r.json() == {"detail": f"perfil '{slug}' não encontrado"}
    assert inexistente.json() == {"detail": "perfil 'nao_existe_de_jeito_nenhum' não encontrado"}
    for h, dentro in ((cena.hx, (PERFIL_PADRAO, cena.G, cena.OX)), (cena.hy, (PERFIL_PADRAO, cena.G, cena.OY))):
        for slug in dentro:
            assert client.get(f"/perfis-jornada/{slug}", headers=h).status_code == 200


def test_edicao_fora_do_escopo_404_geral_ou_padrao_403_409(cena):
    put = lambda h, slug, corpo=None: client.put(f"/perfis-jornada/{slug}", headers=h, json=corpo or PARAMETROS)  # noqa: E731
    r = put(cena.hx, cena.OX, {"nome": "Renomeado por X", "sindicato": "Sind X"})
    assert r.status_code == 200 and r.json()["nome"] == "Renomeado por X" and r.json()["editavel"] is True
    assert put(cena.hx, cena.OX).status_code == 200  # parâmetros também
    assert put(cena.hx, cena.OY).status_code == 404  # de outro prestador
    assert put(cena.hx, cena.L).status_code == 404  # sem dono e não geral
    assert put(cena.hx, "nao_existe_de_jeito_nenhum").status_code == 404  # o admin não cria por PUT
    assert put(cena.hx, cena.G).status_code == 403  # visível, mas geral
    assert put(cena.hx, PERFIL_PADRAO).status_code == 409
    assert put(cena.hy, cena.OX).status_code == 404
    corpo404 = put(cena.hx, cena.OY).json()
    assert corpo404 == put(cena.hx, "nao_existe_de_jeito_nenhum").json() | {"detail": f"perfil '{cena.OY}' não encontrado"}
    # nada mudou nos perfis alheios
    assert client.get(f"/perfis-jornada/{cena.OY}", headers=cena.plat).json()["proprios"] == []
    assert client.get(f"/perfis-jornada/{cena.G}", headers=cena.plat).json()["proprios"] == []
    # só a plataforma mexe no escopo
    for corpo in ({"geral": True}, {"geral": False}, {"prestador_id": cena.py}, {"prestador_id": None}):
        assert put(cena.hx, cena.OX, corpo).status_code == 403, corpo
    assert put(cena.plat, cena.OX, {"geral": True}).status_code == 200


def test_admin_cria_perfil_dele_nunca_geral(cena):
    r = client.post("/perfis-jornada", headers=cena.hx, json={"nome": "Criado por X", "sindicato": "Sind"})
    assert r.status_code == 201, r.text
    novo = r.json()
    cena.slugs.append(novo["perfil"])
    assert (novo["geral"], novo["prestador_id"], novo["editavel"]) == (False, cena.px, True)
    assert novo["perfil"] in _lista(cena.hx) and novo["perfil"] not in _lista(cena.hy)
    assert client.get(f"/perfis-jornada/{novo['perfil']}", headers=cena.hy).status_code == 404
    assert _lista(cena.plat)[novo["perfil"]]["prestador_id"] == cena.px
    for extra in ({"geral": True}, {"geral": False}, {"prestador_id": cena.py}, {"prestador_id": cena.px}):
        r = client.post("/perfis-jornada", headers=cena.hx, json={"nome": "Tentativa", **extra})
        assert r.status_code == 403, extra
    assert client.put(f"/perfis-jornada/{novo['perfil']}", headers=cena.hx, json=PARAMETROS).status_code == 200
    assert client.put(f"/perfis-jornada/{novo['perfil']}", headers=cena.hy, json=PARAMETROS).status_code == 404


def test_plataforma_cria_geral_ou_de_prestador_e_marca_desmarca_geral(cena):
    assert client.post("/perfis-jornada", headers=cena.plat,
                       json={"nome": "Dono inexistente", "prestador_id": 2 ** 62}).status_code == 404
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.plat, json={"prestador_id": 2 ** 62}).status_code == 404
    assert cena.L not in _lista(cena.hx)
    r = client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"geral": True})  # marca geral
    assert r.status_code == 200 and r.json()["geral"] is True
    assert cena.L in _lista(cena.hx) and cena.L in _lista(cena.hy)
    assert client.get(f"/perfis-jornada/{cena.L}", headers=cena.hx).json()["editavel"] is False
    r = client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"geral": False})  # desmarca
    assert r.json()["geral"] is False and cena.L not in _lista(cena.hx)
    assert client.get(f"/perfis-jornada/{cena.L}", headers=cena.hx).status_code == 404
    r = client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"prestador_id": cena.py})  # atribui a Y
    assert r.json()["prestador_id"] == cena.py and cena.L in _lista(cena.hy) and cena.L not in _lista(cena.hx)
    assert client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"prestador_id": None}).json()["prestador_id"] is None
    assert client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"geral": None}).status_code == 422


def test_associar_so_perfil_que_ele_ve(cena):
    assoc = lambda h, contrato, slug: client.put(  # noqa: E731
        f"/contratos/{contrato}/perfil-jornada", headers=h, json={"perfil": slug})
    for ok in (cena.OX, cena.G, PERFIL_PADRAO):
        r = assoc(cena.hx, cena.cx, ok)
        assert r.status_code == 200 and r.json()["perfil_jornada"] == ok and r.json()["perfil_jornada_visivel"] is True
    assert assoc(cena.hx, cena.cx, cena.G).json()["perfil_jornada_nome"] == "Geral"
    for fora in (cena.OY, cena.L, "nao_existe_de_jeito_nenhum"):
        r = assoc(cena.hx, cena.cx, fora)
        assert r.status_code == 404 and r.json() == {"detail": f"perfil '{fora}' não encontrado"}, fora
    assert cena.mundo.db.execute("SELECT perfil_jornada FROM contrato WHERE id = %s", (cena.cx,)).fetchone()[0] == cena.G
    assert assoc(cena.hx, cena.cy, cena.G).status_code == 403  # contrato de outra empresa: regra de sempre
    assert assoc(cena.plat, cena.cx, cena.OY).status_code == 200  # a plataforma associa qualquer um


def test_contrato_com_perfil_fora_do_escopo_continua_funcionando_e_mostra_so_que_existe(cena):
    assert client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=cena.plat, json={"perfil": cena.OY}).status_code == 200
    contrato = {c["id"]: c for c in client.get("/contratos", headers=cena.hx).json()}[cena.cx]
    assert contrato["perfil_jornada"] == cena.OY  # o slug aparece: o perfil existe
    assert contrato["perfil_jornada_visivel"] is False and contrato["perfil_jornada_nome"] is None  # sem detalhes
    assert client.get(f"/perfis-jornada/{cena.OY}", headers=cena.hx).status_code == 404
    visto_pela_plataforma = {c["id"]: c for c in client.get("/contratos", headers=cena.plat).json()}[cena.cx]
    assert visto_pela_plataforma["perfil_jornada_visivel"] is True and visto_pela_plataforma["perfil_jornada_nome"] == "Dono Y"
    with psycopg.connect(config.DATABASE_URL) as conn:  # a análise usa o perfil do contrato, sem filtro de escopo
        assert carregar_perfil(conn, cena.OY)
    # perfil visível no contrato: nome presente
    client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=cena.hx, json={"perfil": cena.OX})
    contrato = {c["id"]: c for c in client.get("/contratos", headers=cena.hx).json()}[cena.cx]
    assert (contrato["perfil_jornada_visivel"], contrato["perfil_jornada_nome"]) == (True, "Dono X")


def test_contagem_de_contratos_so_do_escopo_do_admin(cena):
    client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=cena.hx, json={"perfil": cena.G})
    client.put(f"/contratos/{cena.cy}/perfil-jornada", headers=cena.hy, json={"perfil": cena.G})
    assert _lista(cena.hx)[cena.G]["contratos"] == 1 and _lista(cena.hy)[cena.G]["contratos"] == 1
    assert _lista(cena.plat)[cena.G]["contratos"] == 2


def test_tomador_e_prestador_comum_continuam_sem_acesso(cena):
    mundo = cena.mundo
    t, p = mundo.tomador(), mundo.prestador()
    mundo.contrato(t, p)
    comuns = [_h_id(mundo.usuario("prestador", "admin", prestador_id=p)),  # terceirizada: contrato não próprio
              _h_id(mundo.usuario("prestador", "membro", prestador_id=cena.px)),
              _h_id(mundo.usuario("tomador", "admin", tomador_id=t)),
              _h_id(mundo.usuario("tomador", "membro", tomador_id=t))]
    for h in comuns:
        assert client.get("/perfis-jornada", headers=h).status_code == 403
        assert client.get(f"/perfis-jornada/{cena.G}", headers=h).status_code == 403
        assert client.post("/perfis-jornada", headers=h, json={"nome": "x"}).status_code == 403
        assert client.put(f"/perfis-jornada/{cena.G}", headers=h, json=PARAMETROS).status_code == 403
        assert client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=h, json={"perfil": cena.G}).status_code == 403
    assert client.get("/perfis-jornada").status_code == 401
    # leitura de contratos por quem não lê perfis: o slug aparece, sem nome nem detalhes
    contrato = {c["id"]: c for c in client.get("/contratos", headers=comuns[0]).json()}
    assert all(c["perfil_jornada_visivel"] is False and c["perfil_jornada_nome"] is None for c in contrato.values())


# ---------- revisão: oráculo de slug, geral x dono, 404/422, perda de acesso, análise ----------

def test_slug_nao_revela_perfis_de_outros_escopos(cena):
    resp = {}
    for quem, h in (("x", cena.hx), ("y", cena.hy), ("plat", cena.plat)):
        resp[quem] = [client.post("/perfis-jornada", headers=h, json={"nome": "Acordo X"}) for _ in range(2)]
        for r in resp[quem]:
            assert r.status_code == 201, r.text
            cena.slugs.append(r.json()["perfil"])
    todos = [r for lista in resp.values() for r in lista]
    assert len({r.json()["perfil"] for r in todos}) == 6  # nunca repete
    assert all(re.fullmatch(r"acordo_x_[a-z0-9]{6}", r.json()["perfil"]) for r in todos)  # nunca `_2`
    chaves = {tuple(sorted(r.json())) for r in todos}
    assert len(chaves) == 1  # mesmo formato para quem já tem e para quem não tem um "Acordo X"


def test_geral_e_dono_sao_exclusivos(cena):
    post = lambda corpo: client.post("/perfis-jornada", headers=cena.plat, json=corpo)  # noqa: E731
    assert post({"nome": "Os dois", "geral": True, "prestador_id": cena.px}).status_code == 422
    assert post({"nome": "Geral nulo", "geral": None}).status_code == 422
    assert post({"nome": "Geral texto", "geral": "true"}).status_code == 422
    assert post({"nome": "Geral numero", "geral": 1}).status_code == 422
    put = lambda slug, corpo: client.put(f"/perfis-jornada/{slug}", headers=cena.plat, json=corpo)  # noqa: E731
    assert put(cena.OX, {"geral": True, "prestador_id": cena.px}).status_code == 422
    assert put(cena.OX, {"geral": None}).status_code == 422
    assert put(cena.G, {"prestador_id": cena.px}).status_code == 422  # geral sem desmarcar
    r = put(cena.G, {"geral": False, "prestador_id": cena.px})
    assert r.status_code == 200 and (r.json()["geral"], r.json()["prestador_id"]) == (False, cena.px)
    with pytest.raises(psycopg.errors.CheckViolation):  # e o banco recusa a combinação
        cena.mundo.db.execute("UPDATE perfil_jornada_cadastro SET geral = true WHERE perfil = %s", (cena.OX,))


def test_promover_perfil_de_x_a_geral_tira_o_dono_e_a_edicao_dele(cena):
    r = client.put(f"/perfis-jornada/{cena.OX}", headers=cena.plat, json={"geral": True})
    assert r.status_code == 200 and (r.json()["geral"], r.json()["prestador_id"]) == (True, None)
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.hx, json={"nome": "Mudou"}).status_code == 403
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.hx, json=PARAMETROS).status_code == 403
    assert client.get(f"/perfis-jornada/{cena.OX}", headers=cena.hx).json()["editavel"] is False
    visto_por_y = client.get(f"/perfis-jornada/{cena.OX}", headers=cena.hy)
    assert visto_por_y.status_code == 200 and visto_por_y.json()["editavel"] is False
    r = client.put(f"/contratos/{cena.cy}/perfil-jornada", headers=cena.hy, json={"perfil": cena.OX})
    assert r.status_code == 200 and r.json()["perfil_jornada"] == cena.OX
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.hy, json={"nome": "Y tenta"}).status_code == 403


def test_hx_nao_descobre_perfil_de_y_pelo_put(cena):
    inexistente = client.put("/perfis-jornada/nao_existe_de_jeito_nenhum", headers=cena.hx, json={"geral": True})
    for corpo in ({"geral": True}, {"prestador_id": cena.px}, {"geral": False}, {"nome": "x"}, PARAMETROS):
        r = client.put(f"/perfis-jornada/{cena.OY}", headers=cena.hx, json=corpo)
        assert r.status_code == 404 == inexistente.status_code, corpo
        assert r.json() == {"detail": f"perfil '{cena.OY}' não encontrado"}
    assert client.get(f"/perfis-jornada/{cena.OY}", headers=cena.plat).json()["prestador_id"] == cena.py


def test_prestador_apagado_entre_a_checagem_e_a_gravacao_da_404(cena, monkeypatch):
    from app.routers.perfis_jornada import actions
    monkeypatch.setattr(actions, "_exigir_prestador", lambda session, prestador_id: None)  # simula a corrida
    r = client.post("/perfis-jornada", headers=cena.plat, json={"nome": "Corrida", "prestador_id": 2 ** 40})
    assert r.status_code == 404 and r.json() == {"detail": f"prestador {2 ** 40} não encontrado"}
    r = client.put(f"/perfis-jornada/{cena.L}", headers=cena.plat, json={"prestador_id": 2 ** 40})
    assert r.status_code == 404 and r.json() == {"detail": f"prestador {2 ** 40} não encontrado"}
    assert client.get(f"/perfis-jornada/{cena.L}", headers=cena.plat).json()["prestador_id"] is None


@pytest.mark.parametrize("onde", ["contrato", "tomador", "prestador"])
def test_admin_perde_acesso_com_contrato_tomador_ou_prestador_inativo(cena, onde):
    db = cena.mundo.db
    tomador = db.execute("SELECT tomador_id FROM contrato WHERE id = %s", (cena.cx,)).fetchone()[0]
    assert client.get("/perfis-jornada", headers=cena.hx).status_code == 200
    if onde == "contrato":
        db.execute("UPDATE contrato SET ativo = false WHERE id = %s", (cena.cx,))
    elif onde == "tomador":
        db.execute("UPDATE tomador SET ativo = false WHERE id = %s", (tomador,))
    else:
        db.execute("UPDATE prestador SET ativo = false WHERE id = %s", (cena.px,))
    negado = 401 if onde == "prestador" else 403  # prestador inativo: o login já não vale (401); os outros: 403
    assert client.get("/perfis-jornada", headers=cena.hx).status_code == negado
    assert client.get(f"/perfis-jornada/{cena.OX}", headers=cena.hx).status_code == negado
    assert client.post("/perfis-jornada", headers=cena.hx, json={"nome": "x"}).status_code == negado
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.hx, json={"nome": "x"}).status_code == negado
    assert client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=cena.hx,
                      json={"perfil": cena.OX}).status_code == negado
    assert client.get("/perfis-jornada", headers=cena.hy).status_code == 200  # a outra empresa não é afetada


def test_listagem_conta_parametros_so_do_escopo(cena):
    assert client.put(f"/perfis-jornada/{cena.OY}", headers=cena.plat, json=PARAMETROS).status_code == 200
    assert client.put(f"/perfis-jornada/{cena.OX}", headers=cena.hx, json=PARAMETROS).status_code == 200
    lx = _lista(cena.hx)
    assert lx[cena.OX]["parametros_proprios"] == 1 and cena.OY not in lx
    assert _lista(cena.hy)[cena.OY]["parametros_proprios"] == 1


def test_analise_de_ponto_usa_perfil_fora_do_escopo_do_admin(cena, rede):  # noqa: F811
    """Contrato ligado (pela plataforma) a um perfil que o admin não vê: a análise usa esse perfil mesmo assim."""
    assert client.put(f"/perfis-jornada/{cena.OY}", headers=cena.plat, json={"parametros": [
        {"parametro": "extras_max_dia_min", "valor": 300, "base_legal": "ACT de Y"}]}).status_code == 200
    assert client.put(f"/contratos/{cena.cx}/perfil-jornada", headers=cena.plat, json={"perfil": cena.OY}).status_code == 200
    assert client.get(f"/perfis-jornada/{cena.OY}", headers=cena.hx).status_code == 404
    lote, doc = _doc()
    try:
        cena.mundo.db.execute("UPDATE lote SET contrato_id = %s WHERE id = %s", (cena.cx, lote))
        rede["gemini"].append(_gemini(IRREGULAR))
        rede["jev"].append(lambda corpo: _jev(corpo, {}))
        analise.analisar_documento({"documento_id": doc})
        perfil_nome, perfil, divs = cena.mundo.db.execute(
            "SELECT perfil_nome, perfil, divergencias FROM analise_ponto WHERE documento_id = %s", (doc,)).fetchone()
        assert perfil_nome == cena.OY and perfil["extras_max_dia_min"] == {"valor": 300, "base_legal": "ACT de Y"}
        assert "horas_extras_acima_limite" not in [d["tipo"] for d in divs]  # 4h extras cabem nos 300 min do perfil de Y
        r = client.get(f"/documentos/{doc}/analise-ponto", headers=cena.hx)
        assert r.status_code == 200 and r.json()["perfil_nome"] == cena.OY
        assert r.json()["perfil"]["extras_max_dia_min"]["valor"] == 300
    finally:
        cena.mundo.db.execute("DELETE FROM lote WHERE id = %s", (lote,))
