"""cadastro do perfil de jornada: nome, sindicato e vigência

Revision ID: 0010_perfil_jornada_cadastro
Revises: 0009_contrato_proprio

Upgrade: tabela `perfil_jornada_cadastro`, uma linha por perfil (chave = o slug de `perfil_jornada.perfil`), com
`nome` (obrigatório), `sindicato` (opcional) e `vigencia_inicio`/`vigencia_fim` (opcionais; fim >= início).
Populada com um registro por perfil existente: `clt_padrao` recebe o nome "Padrão"; os demais, o nome derivado do
slug (`adm_publica` -> "Adm publica"). `perfil_jornada` não muda.

Downgrade: remove a tabela (nome, sindicato e vigência são PERDIDOS; os parâmetros dos perfis ficam).
"""
from alembic import op

revision = "0010_perfil_jornada_cadastro"
down_revision = "0009_contrato_proprio"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE perfil_jornada_cadastro (
    perfil          TEXT PRIMARY KEY,
    nome            TEXT NOT NULL CHECK (btrim(nome) <> ''),
    sindicato       TEXT,
    vigencia_inicio DATE,
    vigencia_fim    DATE,
    CONSTRAINT perfil_jornada_cadastro_vigencia_check
        CHECK (vigencia_inicio IS NULL OR vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio)
);

INSERT INTO perfil_jornada_cadastro (perfil, nome)
SELECT perfil,
       CASE WHEN perfil = 'clt_padrao' THEN 'Padrão'
            ELSE upper(left(replace(perfil, '_', ' '), 1)) || substr(replace(perfil, '_', ' '), 2) END
  FROM (SELECT DISTINCT perfil FROM perfil_jornada) p;
"""

DOWNGRADE = r"""
DROP TABLE perfil_jornada_cadastro;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
