"""Testes nunca chamam a rede: _enviar é bloqueado, o cache vai para um diretório temporário e o
classificador padrão é o de regras. Testes de LLM trocam _enviar por um mock e CLASSIFICADOR por 'jev'."""
import httpx
import pytest

from app import config, llm


@pytest.fixture(autouse=True)
def sem_rede(monkeypatch, tmp_path):
    def bloqueado(url, headers, corpo):
        raise httpx.ConnectError("rede bloqueada nos testes")
    monkeypatch.setattr(llm, "_enviar", bloqueado)
    monkeypatch.setattr(config, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(config, "CLASSIFICADOR", "regras")
    monkeypatch.setattr(config, "LLM_ESPERA", 0.0)
    monkeypatch.setattr(config, "OPENROUTER_API_KEY", "chave-falsa-teste")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "chave-falsa-teste")
    monkeypatch.setattr(config, "JEV_MODEL", "jev-teste")


@pytest.fixture(autouse=True)
def autenticacao(monkeypatch):
    """Valores falsos de autenticação e a dependência de login substituída, para os testes de rotas não
    precisarem de token. tests/test_autenticacao.py remove o override (fixture `auth_real`)."""
    from app.api import app
    from app.routers.auth.actions import UsuarioContexto, exigir_usuario
    monkeypatch.setattr(config, "AUTH_USUARIO", "usuario-teste")
    monkeypatch.setattr(config, "AUTH_SENHA", "senha-falsa-teste")
    monkeypatch.setattr(config, "AUTH_SEGREDO", "segredo-falso-de-teste-com-mais-de-32-bytes")
    monkeypatch.setattr(config, "AUTH_EXPIRA_MIN", 480)
    falso = UsuarioContexto(id=0, email="admin-falso@exemplo.invalid", nome="Admin Falso", nivel="plataforma",
                            papel="admin", tomador_id=None, prestador_id=None)
    app.dependency_overrides[exigir_usuario] = lambda: falso
    yield
    app.dependency_overrides.pop(exigir_usuario, None)


@pytest.fixture
def auth_real():
    """Desliga o override: a autenticação passa a valer de verdade."""
    from app.api import app
    from app.routers.auth.actions import exigir_usuario
    app.dependency_overrides.pop(exigir_usuario, None)


@pytest.fixture(autouse=True)
def extracoes(monkeypatch):
    """Não enfileira extração de verdade (o worker do compose chamaria o Gemini). Devolve os ids pedidos."""
    from app import extracao
    from app.routers.revisao import actions as revisao_actions
    class Pedidas(list):
        forcadas: list
    pedidas = Pedidas()
    pedidas.forcadas = []

    def registrar(documento_id, r=None, forcar=False):
        pedidas.append(documento_id)
        if forcar:
            pedidas.forcadas.append(documento_id)  # pedidos feitos pela revisão humana (payload forcar)
    registrar.__wrapped__ = extracao.enfileirar_extracao  # a função real, para testá-la
    monkeypatch.setattr(extracao, "enfileirar_extracao", registrar)
    monkeypatch.setattr(revisao_actions, "enfileirar_extracao", registrar)
    from app.routers.documentos import actions as documentos_actions
    monkeypatch.setattr(documentos_actions, "enfileirar_extracao", registrar)
    return pedidas


def cnpj_valido(base: int) -> str:
    """CNPJ de teste (não é de empresa real) com dígitos verificadores corretos, a partir de um inteiro de 8 dígitos
    (a filial 0001 é fixa)."""
    c = f"{base % 10 ** 8:08d}0001"
    for pesos in ([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]):
        resto = sum(int(d) * p for d, p in zip(c, pesos)) % 11
        c += str(0 if resto < 2 else 11 - resto)
    return c


@pytest.fixture
def orgs():
    """Cria tomador, prestador e contrato direto no banco e apaga tudo no fim (lotes dos contratos primeiro,
    depois contratos, prestadores e tomadores). Devolve um objeto com os criadores."""
    import uuid

    import psycopg

    conn = psycopg.connect(config.DATABASE_URL, autocommit=True)
    criados = {"tomador": [], "prestador": [], "contrato": []}

    class Ajuda:
        db = conn

        @staticmethod
        def tomador(ativo=True):
            i = conn.execute("INSERT INTO tomador (nome, ativo) VALUES (%s, %s) RETURNING id",
                             (f"Tomador {uuid.uuid4().hex}", ativo)).fetchone()[0]
            criados["tomador"].append(i)
            return i

        @staticmethod
        def prestador(ativo=True):
            cnpj = cnpj_valido(uuid.uuid4().int)
            i = conn.execute("INSERT INTO prestador (cnpj, razao_social, ativo) VALUES (%s, %s, %s) RETURNING id",
                             (cnpj, f"Prestador {uuid.uuid4().hex}", ativo)).fetchone()[0]
            criados["prestador"].append(i)
            return i

        @staticmethod
        def contrato(ativo=True, tomador_ativo=True, prestador_ativo=True):
            i = conn.execute(
                "INSERT INTO contrato (tomador_id, prestador_id, ativo) VALUES (%s, %s, %s) RETURNING id",
                (Ajuda.tomador(tomador_ativo), Ajuda.prestador(prestador_ativo), ativo)).fetchone()[0]
            criados["contrato"].append(i)
            return i

        @staticmethod
        def registrar(tipo, id_):
            """Para o que o teste criou pela API."""
            criados[tipo].append(id_)

    yield Ajuda
    conn.execute("DELETE FROM lote WHERE contrato_id = ANY(%s)", (criados["contrato"],))
    conn.execute("DELETE FROM contrato WHERE id = ANY(%s)", (criados["contrato"],))
    conn.execute("DELETE FROM prestador WHERE id = ANY(%s)", (criados["prestador"],))
    conn.execute("DELETE FROM tomador WHERE id = ANY(%s)", (criados["tomador"],))
    conn.close()


@pytest.fixture
def sessao():
    """Sessão SQLAlchemy para chamar actions direto (as rotas recebem a delas por Depends(get_session)).
    Fecha no fim do teste; quem escreve faz o commit na própria action, como na requisição."""
    from app.database import SessionLocal
    s = SessionLocal()
    yield s
    s.close()
