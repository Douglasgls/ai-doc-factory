"""Cria o primeiro administrador da plataforma a partir de AUTH_USUARIO e AUTH_SENHA. Idempotente:
se já existe usuário com esse identificador, não altera nada (nem a senha). Uso: python -m app.bootstrap_admin
Roda no serviço `migrate` do compose, depois do `alembic upgrade head`. Nunca imprime senha nem hash."""
import logging
import sys

import psycopg

from app import config, senhas

log = logging.getLogger("bootstrap_admin")
NOME_ADMIN = "Administrador"


def executar() -> str:
    """Devolve 'ignorado' (variáveis ausentes), 'criado', 'existente' ou 'senha_longa'."""
    email, senha = config.AUTH_USUARIO.strip(), config.AUTH_SENHA
    if not email or not senha:
        log.info("AUTH_USUARIO/AUTH_SENHA não definidos: nenhum administrador criado")
        return "ignorado"
    if not senhas.senha_valida_tamanho(senha):
        log.error("AUTH_SENHA acima do limite de %d bytes: administrador não criado", senhas.SENHA_MAX_BYTES)
        return "senha_longa"
    with psycopg.connect(config.DATABASE_URL) as conn:
        if conn.execute("SELECT 1 FROM usuario WHERE lower(email) = lower(%s)", (email,)).fetchone():
            log.info("usuário '%s' já existe: nada alterado", email)
            return "existente"
        # ON CONFLICT cobre a corrida entre duas execuções simultâneas.
        criado = conn.execute(
            "INSERT INTO usuario (email, nome, senha_hash, nivel, papel) VALUES (%s, %s, %s, 'plataforma', 'admin') "
            "ON CONFLICT (lower(email)) DO NOTHING RETURNING id",
            (email, NOME_ADMIN, senhas.gerar_hash(senha))).fetchone()
    log.info("administrador '%s' criado (nível plataforma)" if criado else "usuário '%s' já existe: nada alterado", email)
    return "criado" if criado else "existente"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    return 1 if executar() == "senha_longa" else 0


if __name__ == "__main__":
    sys.exit(main())
