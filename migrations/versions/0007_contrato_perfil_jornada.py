"""contrato aponta para um perfil de jornada; a análise de ponto grava o nome do perfil usado

Revision ID: 0007_contrato_perfil_jornada
Revises: 0006_perfil_jornada_vigencia

Upgrade:
- `contrato.perfil_jornada` (TEXT, padrão 'clt_padrao'): nome do perfil em `perfil_jornada`. Não há chave
  estrangeira (o perfil é um conjunto de linhas, não uma linha): a API só associa perfil que existe e não apaga
  perfil. Contratos existentes ficam com 'clt_padrao'.
- `analise_ponto.perfil_nome` (TEXT, NULL nas análises antigas, que usaram 'clt_padrao').

Um perfil próprio guarda só os parâmetros que diferem; o resto é herdado de 'clt_padrao' (app/ponto.py).

Downgrade: remove as duas colunas (a associação de cada contrato é PERDIDA). As linhas de perfis próprios em
`perfil_jornada` ficam (a tabela sempre aceitou outros perfis), mas deixam de ser usadas.
"""
from alembic import op

revision = "0007_contrato_perfil_jornada"
down_revision = "0006_perfil_jornada_vigencia"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE contrato ADD COLUMN perfil_jornada TEXT NOT NULL DEFAULT 'clt_padrao';
ALTER TABLE analise_ponto ADD COLUMN perfil_nome TEXT;
"""

DOWNGRADE = r"""
ALTER TABLE analise_ponto DROP COLUMN perfil_nome;
ALTER TABLE contrato DROP COLUMN perfil_jornada;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
