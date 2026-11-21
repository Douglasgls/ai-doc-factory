"""documento_campos.autor: e-mail do usuário que corrigiu o campo

Revision ID: 0008_documento_campos_autor
Revises: 0007_contrato_perfil_jornada

Upgrade: `documento_campos.autor` (TEXT, NULL). Preenchido só nas correções humanas (origem 'humano') com o
e-mail do usuário autenticado; a extração do Gemini deixa NULL. Linhas existentes ficam NULL.

Downgrade: remove a coluna (a autoria das correções é PERDIDA).
"""
from alembic import op

revision = "0008_documento_campos_autor"
down_revision = "0007_contrato_perfil_jornada"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE documento_campos ADD COLUMN autor TEXT;
"""

DOWNGRADE = r"""
ALTER TABLE documento_campos DROP COLUMN autor;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
