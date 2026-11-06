import urllib.error
from unittest import mock

import pytest

from scripts import api_http


def test_envia_bearer_do_ambiente(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "abc")
    vistos = []
    with mock.patch("urllib.request.urlopen", side_effect=lambda req: vistos.append(req) or "ok"):
        assert api_http.abrir("http://x/lotes/1") == "ok"
    assert vistos[0].get_header("Authorization") == "Bearer abc"


def test_sem_token_nao_envia_cabecalho(monkeypatch):
    monkeypatch.delenv("API_TOKEN", raising=False)
    vistos = []
    with mock.patch("urllib.request.urlopen", side_effect=lambda req: vistos.append(req) or "ok"):
        api_http.abrir("http://x")
    assert vistos[0].get_header("Authorization") is None


def test_401_gera_mensagem_clara(monkeypatch):
    erro = urllib.error.HTTPError("http://x", 401, "Unauthorized", {}, None)
    with mock.patch("urllib.request.urlopen", side_effect=erro):
        with pytest.raises(SystemExit) as e:
            api_http.abrir("http://x")
    assert "API_TOKEN" in str(e.value)
