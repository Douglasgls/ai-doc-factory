"""Módulo de senhas (scrypt). Só valores falsos de teste."""
import pytest

from app import senhas

SENHA = "senha-falsa-teste"
FRACO = dict(n=2 ** 10, r=8, p=1)  # custo baixo e rápido para montar hashes antigos


def test_formato_autodescritivo():
    h = senhas.gerar_hash(SENHA)
    algoritmo, n, r, p, sal, derivado = h.split("$")
    assert algoritmo == "scrypt"
    assert (int(n), int(r), int(p)) == (senhas.SCRYPT_N, senhas.SCRYPT_R, senhas.SCRYPT_P)
    assert sal and derivado and SENHA not in h


def test_mesma_senha_gera_hashes_diferentes():
    assert senhas.gerar_hash(SENHA) != senhas.gerar_hash(SENHA)


def test_verificacao_correta_e_incorreta():
    h = senhas.gerar_hash(SENHA, **FRACO)
    assert senhas.verificar(SENHA, h) is True
    assert senhas.verificar(SENHA + "x", h) is False
    assert senhas.verificar("", h) is False


@pytest.mark.parametrize("ruim", [None, "", "lixo", "scrypt$1$2", "bcrypt$1024$8$1$YQ==$YQ==",
                                  "scrypt$abc$8$1$YQ==$YQ==", "scrypt$1000$8$1$YQ==$YQ==",  # N não é potência de 2
                                  "scrypt$1024$8$1$@@@$YQ==", "scrypt$1024$8$1$$", "scrypt$0$8$1$YQ==$YQ==",
                                  f"scrypt${2 ** 40}$8$1$YQ==$YQ==", "scrypt$1024$8$999$YQ==$YQ=="])
def test_hash_malformado_devolve_false(ruim):
    assert senhas.verificar(SENHA, ruim) is False
    assert senhas.precisa_rehash(ruim) is False


def test_senha_acima_do_limite_e_recusada():
    longa = "a" * (senhas.SENHA_MAX_BYTES + 1)
    with pytest.raises(ValueError):
        senhas.gerar_hash(longa)
    h = senhas.gerar_hash("a" * senhas.SENHA_MAX_BYTES, **FRACO)  # no limite passa
    assert senhas.verificar("a" * senhas.SENHA_MAX_BYTES, h)
    assert senhas.verificar(longa, h) is False
    # o limite é em bytes: 600 caracteres de 2 bytes passam do teto
    assert senhas.verificar("ç" * 600, h) is False


def test_precisa_rehash_quando_custo_abaixo_do_atual():
    assert senhas.precisa_rehash(senhas.gerar_hash(SENHA, **FRACO)) is True
    assert senhas.precisa_rehash(senhas.gerar_hash(SENHA)) is False


def test_hash_antigo_continua_verificando_apos_aumentar_o_custo(monkeypatch):
    antigo = senhas.gerar_hash(SENHA, **FRACO)
    monkeypatch.setattr(senhas, "SCRYPT_N", 2 ** 11)
    assert senhas.verificar(SENHA, antigo) is True
    assert senhas.precisa_rehash(antigo) is True
