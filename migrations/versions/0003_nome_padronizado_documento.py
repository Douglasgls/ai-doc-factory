"""nome_padronizado na tabela documento para renomeação automática

Revision ID: 0003_nome_padronizado_documento
Revises: 0002_modelo_acesso
"""
from alembic import op

revision = "0003_nome_padronizado_documento"
down_revision = "0002_modelo_acesso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE documento ADD COLUMN IF NOT EXISTS nome_padronizado TEXT"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE documento DROP COLUMN IF EXISTS nome_padronizado"
    )

