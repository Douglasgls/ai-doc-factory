"""coluna texto_nativo na tabela pagina para distinguir PDF digital de OCR

Revision ID: 0012_pagina_texto_nativo
Revises: 0011_perfil_jornada_escopo

Upgrade: `pagina.texto_nativo` (BOOLEAN NOT NULL DEFAULT false). Indica se o texto da página foi extraído
diretamente da camada digital do PDF via PyMuPDF (true) ou via rasterização + Tesseract OCR (false).

Downgrade: remove a coluna `texto_nativo`.
"""
from alembic import op

revision = "0012_pagina_texto_nativo"
down_revision = "0011_perfil_jornada_escopo"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE pagina ADD COLUMN texto_nativo BOOLEAN NOT NULL DEFAULT false;
"""

DOWNGRADE = r"""
ALTER TABLE pagina DROP COLUMN texto_nativo;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)

