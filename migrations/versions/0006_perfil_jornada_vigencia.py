"""perfil_jornada com vigência por data; EC 141/2026 no perfil clt_padrao

Revision ID: 0006_perfil_jornada_vigencia
Revises: 0005_convite

Upgrade:
- `perfil_jornada.vigente_desde` (DATE, NULL = valor de base, vale desde sempre). O valor de um parâmetro numa data é
  o da linha com a maior `vigente_desde` que não passa da data; sem nenhuma, vale a linha de base.
- A unicidade passa de (perfil, parametro) para (perfil, parametro, vigente_desde), com NULLs iguais entre si
  (uma única linha de base por parâmetro).
- Emenda Constitucional 141, de 16/10/2026 (DOU de 16/10/2026, edição extra; texto conferido em 15/11/2026 em
  planalto.gov.br/ccivil_03/constituicao/emendas/emc/emc141.htm):
  - art. 6º, I: "2 (dois) meses após a publicação", duração normal de até 42 horas semanais -> 16/12/2026;
  - art. 6º, II: "1 (um) ano após o decurso do prazo" do inciso I, até 40 horas semanais -> 16/12/2027;
  - art. 7º, XV, da CF: "repouso semanal remunerado de 2 (dois) dias", em vigor "após decorridos 2 (dois) meses"
    da publicação (art. 10, I) -> 16/12/2026.
  As datas ficam SÓ aqui (e no banco). Contratos com a administração pública (EC 141, art. 9º) não têm regra
  automática: usam um perfil próprio.
- Novo parâmetro `repouso_semanal_dias`: 0 = a regra de dias não se aplica e vale só o descanso contínuo de
  `descanso_semanal_min` (CLT art. 67); a partir de 16/12/2026, 2.
- A base legal das 44 horas deixa de citar a CLT (o limite semanal vinha só da CF art. 7º, XIII).

Downgrade: remove TODAS as linhas com `vigente_desde` preenchida e o parâmetro `repouso_semanal_dias` (de qualquer
perfil), restaura a unicidade e a base legal antigas e remove a coluna. As análises já gravadas não mudam.
"""
from alembic import op

revision = "0006_perfil_jornada_vigencia"
down_revision = "0005_convite"
branch_labels = None
depends_on = None

UPGRADE = r"""
ALTER TABLE perfil_jornada ADD COLUMN vigente_desde DATE;
ALTER TABLE perfil_jornada DROP CONSTRAINT perfil_jornada_perfil_parametro_key;
ALTER TABLE perfil_jornada ADD CONSTRAINT perfil_jornada_perfil_parametro_vigente_key
    UNIQUE NULLS NOT DISTINCT (perfil, parametro, vigente_desde);

UPDATE perfil_jornada SET base_legal = 'CF art. 7º, XIII (redação anterior à EC 141/2026)'
 WHERE perfil = 'clt_padrao' AND parametro = 'jornada_semanal_min' AND vigente_desde IS NULL;

INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal, vigente_desde) VALUES
    ('clt_padrao', 'jornada_semanal_min',  2520, 'min', 'CF art. 7º, XIII; EC 141/2026, art. 6º, I',  DATE '2026-12-16'),
    ('clt_padrao', 'jornada_semanal_min',  2400, 'min', 'CF art. 7º, XIII; EC 141/2026, art. 6º, II', DATE '2027-12-16'),
    ('clt_padrao', 'repouso_semanal_dias', 0,    'dia',
     'CLT art. 67 (antes da EC 141/2026 vale o descanso de 24h consecutivas)', NULL),
    ('clt_padrao', 'repouso_semanal_dias', 2,    'dia',
     'CF art. 7º, XV (redação da EC 141/2026; art. 10, I)', DATE '2026-12-16');
"""

DOWNGRADE = r"""
DELETE FROM perfil_jornada WHERE vigente_desde IS NOT NULL OR parametro = 'repouso_semanal_dias';
UPDATE perfil_jornada SET base_legal = 'CF art. 7º, XIII; CLT art. 58'
 WHERE perfil = 'clt_padrao' AND parametro = 'jornada_semanal_min';
ALTER TABLE perfil_jornada DROP CONSTRAINT perfil_jornada_perfil_parametro_vigente_key;
ALTER TABLE perfil_jornada DROP COLUMN vigente_desde;
ALTER TABLE perfil_jornada ADD CONSTRAINT perfil_jornada_perfil_parametro_key UNIQUE (perfil, parametro);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(DOWNGRADE)
