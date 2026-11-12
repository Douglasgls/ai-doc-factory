"""Restrições das tabelas do modelo de acesso (migração 0002). Cada teste roda em uma transação que
sofre rollback, então nenhuma linha sobra. Pula se não houver Postgres."""
import psycopg
import pytest
from psycopg import errors

from app import config


@pytest.fixture
def conn():
    try:
        c = psycopg.connect(config.DATABASE_URL, connect_timeout=3)
    except psycopg.OperationalError:
        pytest.skip("Postgres indisponível")
    try:
        yield c
    finally:
        c.rollback()
        c.close()


def _recusa(conn, erro, sql, params=()):
    """Executa dentro de um savepoint; a violação precisa ser do tipo esperado."""
    with pytest.raises(erro):
        with conn.transaction():
            conn.execute(sql, params)


def _tomador(conn, nome="Tomador A", cnpj=None):
    return conn.execute("INSERT INTO tomador (nome, cnpj) VALUES (%s, %s) RETURNING id", (nome, cnpj)).fetchone()[0]


def _prestador(conn, cnpj="11222333000181", razao="Prestador A"):
    return conn.execute(
        "INSERT INTO prestador (cnpj, razao_social) VALUES (%s, %s) RETURNING id", (cnpj, razao)
    ).fetchone()[0]


def _usuario(conn, email, nivel, papel="membro", tomador_id=None, prestador_id=None):
    conn.execute(
        "INSERT INTO usuario (email, nome, nivel, papel, tomador_id, prestador_id) VALUES (%s, 'U', %s, %s, %s, %s)",
        (email, nivel, papel, tomador_id, prestador_id),
    )


@pytest.mark.parametrize("cnpj", ["1234567890123", "123456789012345", "1234567890123a", "12.345.678/0001-9"])
def test_cnpj_invalido_recusado(conn, cnpj):
    # Valor curto: o CHECK recusa (CHAR(14) completa com espaços). Valor longo: o próprio tipo recusa.
    erro = (errors.CheckViolation, errors.StringDataRightTruncation)
    _recusa(conn, erro, "INSERT INTO tomador (nome, cnpj) VALUES ('X', %s)", (cnpj,))
    _recusa(conn, erro, "INSERT INTO prestador (cnpj, razao_social) VALUES (%s, 'X')", (cnpj,))


def test_tomador_cnpj_opcional_e_unico_quando_presente(conn):
    _tomador(conn, "Sem CNPJ 1")
    _tomador(conn, "Sem CNPJ 2")  # vários NULL são permitidos
    _tomador(conn, "Com CNPJ", "11222333000181")
    _recusa(conn, errors.UniqueViolation, "INSERT INTO tomador (nome, cnpj) VALUES ('Outro', '11222333000181')")


def test_prestador_cnpj_obrigatorio_e_unico(conn):
    _recusa(conn, errors.NotNullViolation, "INSERT INTO prestador (razao_social) VALUES ('X')")
    _prestador(conn)
    _recusa(conn, errors.UniqueViolation, "INSERT INTO prestador (cnpj, razao_social) VALUES ('11222333000181', 'Y')")


def test_nome_de_tomador_unico_sem_caixa_nem_espacos(conn):
    _tomador(conn, "Acme Ltda")
    _recusa(conn, errors.UniqueViolation, "INSERT INTO tomador (nome) VALUES ('  ACME ltda ')")


def test_contrato_duplicado_recusado_e_prestador_com_dois_tomadores(conn):
    t1, t2, p = _tomador(conn, "T1"), _tomador(conn, "T2"), _prestador(conn)
    ins = "INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s)"
    conn.execute(ins, (t1, p))
    conn.execute(ins, (t2, p))  # mesmo prestador, outro tomador: permitido
    _recusa(conn, errors.UniqueViolation, ins, (t1, p))


def test_email_unico_sem_diferenciar_caixa(conn):
    _usuario(conn, "Ana@Exemplo.com", "plataforma")
    _recusa(conn, errors.UniqueViolation,
            "INSERT INTO usuario (email, nome, nivel, papel) VALUES ('ana@exemplo.COM', 'Outra', 'plataforma', 'admin')")


def test_nivel_e_papel_fora_da_lista_recusados(conn):
    _recusa(conn, errors.CheckViolation,
            "INSERT INTO usuario (email, nome, nivel, papel) VALUES ('a@x.com', 'A', 'root', 'admin')")
    _recusa(conn, errors.CheckViolation,
            "INSERT INTO usuario (email, nome, nivel, papel) VALUES ('b@x.com', 'B', 'plataforma', 'dono')")


def test_nivel_e_vinculo_incoerentes_recusados_e_validos_aceitos(conn):
    t, p = _tomador(conn), _prestador(conn)
    incoerentes = [
        ("plataforma", t, None), ("plataforma", None, p), ("tomador", None, None), ("tomador", t, p),
        ("tomador", None, p), ("prestador", None, None), ("prestador", t, p), ("prestador", t, None),
    ]
    for i, (nivel, tid, pid) in enumerate(incoerentes):
        with pytest.raises(errors.CheckViolation):
            with conn.transaction():
                _usuario(conn, f"x{i}@x.com", nivel, tomador_id=tid, prestador_id=pid)
    _usuario(conn, "plat@x.com", "plataforma", "admin")
    _usuario(conn, "tom@x.com", "tomador", tomador_id=t)
    _usuario(conn, "prest@x.com", "prestador", prestador_id=p)
    assert conn.execute("SELECT count(*) FROM usuario").fetchone()[0] == 3


def test_apagar_organizacao_com_contrato_ou_usuario_e_recusado(conn):
    t, p = _tomador(conn), _prestador(conn)
    conn.execute("INSERT INTO contrato (tomador_id, prestador_id) VALUES (%s, %s)", (t, p))
    _recusa(conn, errors.ForeignKeyViolation, "DELETE FROM tomador WHERE id = %s", (t,))
    _recusa(conn, errors.ForeignKeyViolation, "DELETE FROM prestador WHERE id = %s", (p,))
    t2, p2 = _tomador(conn, "T2"), _prestador(conn, "99888777000166", "P2")
    _usuario(conn, "u1@x.com", "tomador", tomador_id=t2)
    _usuario(conn, "u2@x.com", "prestador", prestador_id=p2)
    _recusa(conn, errors.ForeignKeyViolation, "DELETE FROM tomador WHERE id = %s", (t2,))
    _recusa(conn, errors.ForeignKeyViolation, "DELETE FROM prestador WHERE id = %s", (p2,))


def _valores_do_check(conn, constraint):
    definicao = conn.execute(
        "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s", (constraint,)
    ).fetchone()[0]
    # Ex.: CHECK ((nivel = ANY (ARRAY['plataforma'::text, 'tomador'::text, ...])))
    return tuple(trecho.split("'")[-1] for trecho in definicao.split("'::text")[:-1])


def test_constantes_batem_com_os_checks_do_banco(conn):
    assert _valores_do_check(conn, "usuario_nivel_check") == config.NIVEIS_ACESSO
    assert _valores_do_check(conn, "usuario_papel_check") == config.PAPEIS
