"""escopo dos perfis de jornada: perfil geral ou de um prestador

Revision ID: 0011_perfil_jornada_escopo
Revises: 0010_perfil_jornada_cadastro

Upgrade: `perfil_jornada_cadastro.geral` (BOOLEAN NOT NULL DEFAULT false) e `prestador_id` (dono, FK para `prestador`,
NULL = sem dono; ON DELETE SET NULL, então apagar o prestador não apaga o perfil). Os perfis existentes ficam
"não gerais e sem dono": só a plataforma os vê até alguém marcá-los como gerais ou atribuí-los a um prestador.
Geral e dono são exclusivos (CHECK): geral = sem dono, e só a plataforma o edita.
O perfil padrão (`clt_padrao`) não usa as colunas: todos que podem ler perfis o veem.

Downgrade: remove as colunas (a marca de geral e o dono são PERDIDOS; os perfis continuam existindo).
"""
from alembic import op

revision = "0011_perfil_jornada_escopo"
down_revision = "0010_perfil_jornada_cadastro"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE perfil_jornada_cadastro ADD COLUMN geral BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE perfil_jornada_cadastro ADD COLUMN prestador_id BIGINT REFERENCES prestador(id) ON DELETE SET NULL;
ALTER TABLE perfil_jornada_cadastro ADD CONSTRAINT perfil_jornada_cadastro_geral_dono_check
    CHECK (NOT (geral AND prestador_id IS NOT NULL));
CREATE INDEX perfil_jornada_cadastro_prestador_idx ON perfil_jornada_cadastro (prestador_id);
"""

DOWNGRADE = r"""
DROP INDEX perfil_jornada_cadastro_prestador_idx;
ALTER TABLE perfil_jornada_cadastro DROP CONSTRAINT perfil_jornada_cadastro_geral_dono_check;
ALTER TABLE perfil_jornada_cadastro DROP COLUMN prestador_id;
ALTER TABLE perfil_jornada_cadastro DROP COLUMN geral;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
