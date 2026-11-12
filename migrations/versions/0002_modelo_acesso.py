"""modelo de acesso: tomador, prestador, contrato e usuario (ainda não usados pela aplicação)

Revision ID: 0002_modelo_acesso
Revises: 0001_baseline
"""
from alembic import op

revision = "0002_modelo_acesso"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

# Os valores de `nivel` e `papel` precisam bater com NIVEIS_ACESSO e PAPEIS em app/config.py
# (tests/test_modelo_acesso.py compara as constantes com os CHECKs lidos do banco).
SCHEMA = r"""
-- Tomador: o cliente que contrata terceiros. CNPJ opcional (só dígitos).
CREATE TABLE tomador (
    id              BIGSERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    cnpj            CHAR(14) UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
    ativo           BOOLEAN NOT NULL DEFAULT true,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX tomador_nome_uniq ON tomador (lower(btrim(nome)));

-- Prestador: a empresa terceirizada, global e identificada pelo CNPJ. O mesmo prestador pode ter
-- contrato com vários tomadores.
CREATE TABLE prestador (
    id              BIGSERIAL PRIMARY KEY,
    cnpj            CHAR(14) NOT NULL UNIQUE CHECK (cnpj ~ '^[0-9]{14}$'),
    razao_social    TEXT NOT NULL,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Contrato entre um tomador e um prestador: a unidade de isolamento dos dados. RESTRICT de propósito:
-- apagar uma organização com contrato é uma decisão explícita, nunca uma cascata silenciosa.
CREATE TABLE contrato (
    id              BIGSERIAL PRIMARY KEY,
    tomador_id      BIGINT NOT NULL REFERENCES tomador(id) ON DELETE RESTRICT,
    prestador_id    BIGINT NOT NULL REFERENCES prestador(id) ON DELETE RESTRICT,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (tomador_id, prestador_id)
);
CREATE INDEX contrato_prestador_idx ON contrato (prestador_id);

-- Usuário de uma organização (ou da plataforma). `senha_hash` NULL = convidado que ainda não definiu senha.
-- O nível determina o vínculo: plataforma sem organização; tomador e prestador com a respectiva organização.
CREATE TABLE usuario (
    id              BIGSERIAL PRIMARY KEY,
    email           TEXT NOT NULL,
    nome            TEXT NOT NULL,
    senha_hash      TEXT,
    nivel           TEXT NOT NULL CONSTRAINT usuario_nivel_check
                    CHECK (nivel IN ('plataforma', 'tomador', 'prestador')),
    papel           TEXT NOT NULL CONSTRAINT usuario_papel_check
                    CHECK (papel IN ('admin', 'membro')),
    tomador_id      BIGINT REFERENCES tomador(id) ON DELETE RESTRICT,
    prestador_id    BIGINT REFERENCES prestador(id) ON DELETE RESTRICT,
    ativo           BOOLEAN NOT NULL DEFAULT true,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT usuario_nivel_vinculo_check CHECK (
        (nivel = 'plataforma' AND tomador_id IS NULL     AND prestador_id IS NULL) OR
        (nivel = 'tomador'    AND tomador_id IS NOT NULL AND prestador_id IS NULL) OR
        (nivel = 'prestador'  AND prestador_id IS NOT NULL AND tomador_id IS NULL)
    )
);
CREATE UNIQUE INDEX usuario_email_uniq ON usuario (lower(email));
CREATE INDEX usuario_tomador_idx ON usuario (tomador_id);
CREATE INDEX usuario_prestador_idx ON usuario (prestador_id);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA)


def downgrade() -> None:
    # Ordem das dependências: usuario e contrato referenciam tomador e prestador.
    op.get_bind().exec_driver_sql("DROP TABLE usuario, contrato, prestador, tomador")
