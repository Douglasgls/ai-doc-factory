"""contrato.proprio: contrato de uma empresa com ela mesma (empresa solo, sem terceirização)

Revision ID: 0009_contrato_proprio
Revises: 0008_documento_campos_autor

Upgrade: `contrato.proprio` (BOOLEAN NOT NULL DEFAULT false). Contratos existentes ficam false. Um contrato próprio
liga o tomador e o prestador de MESMO CNPJ; quem o cria é POST /empresas-proprias.

Downgrade: remove a coluna (a marca de contrato próprio é PERDIDA; os contratos continuam existindo).
"""
from alembic import op

revision = "0009_contrato_proprio"
down_revision = "0008_documento_campos_autor"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE contrato ADD COLUMN proprio BOOLEAN NOT NULL DEFAULT false;
"""

DOWNGRADE = r"""
ALTER TABLE contrato DROP COLUMN proprio;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
