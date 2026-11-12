"""Comando de bootstrap do administrador. Usa o banco real e remove a linha que cria."""
import psycopg
import pytest

from app import bootstrap_admin, config, senhas

EMAIL = "bootstrap-teste@exemplo.invalid"
SENHA = "senha-falsa-bootstrap"


@pytest.fixture
def banco(monkeypatch):
    try:
        conn = psycopg.connect(config.DATABASE_URL, connect_timeout=3, autocommit=True)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    monkeypatch.setattr(config, "AUTH_USUARIO", EMAIL)
    monkeypatch.setattr(config, "AUTH_SENHA", SENHA)
    conn.execute("DELETE FROM usuario WHERE lower(email) = %s", (EMAIL,))
    try:
        yield conn
    finally:
        conn.execute("DELETE FROM usuario WHERE lower(email) = %s", (EMAIL,))
        conn.close()


def _linha(conn):
    return conn.execute("SELECT id, nome, senha_hash, nivel, papel, tomador_id, prestador_id, ativo "
                        "FROM usuario WHERE lower(email) = %s", (EMAIL,)).fetchone()


def test_cria_admin_de_plataforma_com_hash_que_verifica(banco):
    assert bootstrap_admin.executar() == "criado"
    _, _, senha_hash, nivel, papel, tomador, prestador, ativo = _linha(banco)
    assert (nivel, papel, tomador, prestador, ativo) == ("plataforma", "admin", None, None, True)
    assert SENHA not in senha_hash and senhas.verificar(SENHA, senha_hash)


def test_segunda_execucao_nao_altera_nada(banco, monkeypatch, caplog):
    bootstrap_admin.executar()
    antes = _linha(banco)
    monkeypatch.setattr(config, "AUTH_SENHA", "outra-senha-falsa")  # trocar a variável não muda a senha
    with caplog.at_level("INFO", logger="bootstrap_admin"):
        assert bootstrap_admin.executar() == "existente"
    assert _linha(banco) == antes
    assert "já existe" in caplog.text and SENHA not in caplog.text and antes[2] not in caplog.text
    assert banco.execute("SELECT count(*) FROM usuario WHERE lower(email) = %s", (EMAIL,)).fetchone()[0] == 1


def test_identificador_existente_com_outra_caixa_nao_duplica(banco, monkeypatch):
    bootstrap_admin.executar()
    monkeypatch.setattr(config, "AUTH_USUARIO", f"  {EMAIL.upper()} ")
    assert bootstrap_admin.executar() == "existente"


@pytest.mark.parametrize("campo", ["AUTH_USUARIO", "AUTH_SENHA"])
def test_sem_variaveis_nao_faz_nada(banco, monkeypatch, campo):
    monkeypatch.setattr(config, campo, "")
    assert bootstrap_admin.executar() == "ignorado"
    assert _linha(banco) is None


def test_senha_acima_do_limite_nao_cria(banco, monkeypatch):
    monkeypatch.setattr(config, "AUTH_SENHA", "a" * (senhas.SENHA_MAX_BYTES + 1))
    assert bootstrap_admin.executar() == "senha_longa"
    assert _linha(banco) is None
