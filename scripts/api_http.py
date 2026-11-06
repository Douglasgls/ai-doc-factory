"""Acesso HTTP à API para os scripts de avaliação, com login.

O token vem da variável de ambiente API_TOKEN (nunca de argumento de linha de comando, para não ir ao histórico).
Para obter: POST /auth/login com usuario e senha (ver README); o JSON devolvido traz o token.
"""
import os
import sys
import urllib.error
import urllib.request


def _com_token(alvo):
    req = urllib.request.Request(alvo) if isinstance(alvo, str) else alvo
    token = os.environ.get("API_TOKEN", "").strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return req


def abrir(alvo, timeout: float | None = None):
    """Como urllib.request.urlopen, mas envia o Bearer e explica o 401."""
    try:
        if timeout is None:
            return urllib.request.urlopen(_com_token(alvo))
        return urllib.request.urlopen(_com_token(alvo), timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            sys.exit("401 da API: defina API_TOKEN com um token válido (POST /auth/login; ver README).")
        raise
