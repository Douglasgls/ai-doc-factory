"""baseline: schema inicial (empresa, lote, documento, pagina, perfil_jornada, analise_ponto, documento_campos)

Revision ID: 0001_baseline
Revises:
"""
from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Reproduz o antigo sql/schema.sql (que já incluía `empresa`). Os tipos documentais NÃO são
# restringidos aqui: a lista vive em app/config.py.
SCHEMA = r"""
-- Os tipos documentais NÃO são restringidos aqui: a lista vive em app/config.py.

-- Cadastro de empresas (por nome); os lotes podem ser vinculados a uma na hora do upload.
CREATE TABLE empresa (
    id              BIGSERIAL PRIMARY KEY,
    nome            TEXT NOT NULL,
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX empresa_nome_uniq ON empresa (lower(btrim(nome)));

CREATE TABLE lote (
    id              BIGSERIAL PRIMARY KEY,
    sha256          CHAR(64) NOT NULL UNIQUE,          -- idempotência do upload
    nome_arquivo    TEXT NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'recebido'
                    CHECK (estado IN ('recebido', 'ocr', 'classificando', 'concluido', 'erro')),
    docs_pendentes  INTEGER NOT NULL DEFAULT 0 CHECK (docs_pendentes >= 0),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now(),
    empresa_id      BIGINT REFERENCES empresa(id) ON DELETE SET NULL
);
CREATE INDEX lote_empresa_idx ON lote (empresa_id);

CREATE TABLE documento (
    id              BIGSERIAL PRIMARY KEY,
    lote_id         BIGINT NOT NULL REFERENCES lote(id) ON DELETE CASCADE,
    ordem           INTEGER NOT NULL,
    pagina_ini      INTEGER NOT NULL,
    pagina_fim      INTEGER NOT NULL,
    estado          TEXT NOT NULL DEFAULT 'segmentado'
                    CHECK (estado IN ('segmentado', 'classificado', 'em_revisao', 'revisado', 'erro')),
    tipo            TEXT,
    confianca       DOUBLE PRECISION,
    tipo_original   TEXT,                              -- tipo antes da correção humana
    revisor         TEXT,
    revisado_em     TIMESTAMPTZ,
    motivo_revisao  TEXT,                              -- por que foi para a fila de revisão
    modelo          TEXT,
    versao_prompt   TEXT,
    probabilidades  JSONB,
    segunda_opiniao JSONB,                             -- {modelo, versao_prompt, tipo, status} do Gemini
    segmentacao_ambigua BOOLEAN NOT NULL DEFAULT false,  -- fronteira inicial decidida na faixa ambígua
    CHECK (pagina_fim >= pagina_ini),
    UNIQUE (lote_id, ordem)
);

CREATE TABLE pagina (
    id              BIGSERIAL PRIMARY KEY,
    lote_id         BIGINT NOT NULL REFERENCES lote(id) ON DELETE CASCADE,
    numero          INTEGER NOT NULL,
    documento_id    BIGINT REFERENCES documento(id) ON DELETE SET NULL,
    texto           TEXT,
    UNIQUE (lote_id, numero)
);

CREATE INDEX pagina_documento_idx ON pagina (documento_id);
CREATE INDEX pagina_texto_fts_idx ON pagina
    USING GIN (to_tsvector('portuguese', coalesce(texto, '')));

-- Perfil de jornada (Goal 6). Cada parâmetro guarda valor e base legal. Valores de referência da CLT,
-- sem convenção coletiva nem acordo de compensação, que podem alterá-los. Apoio à auditoria, não parecer jurídico.
CREATE TABLE perfil_jornada (
    id          BIGSERIAL PRIMARY KEY,
    perfil      TEXT NOT NULL,
    parametro   TEXT NOT NULL,
    valor       NUMERIC NOT NULL,
    unidade     TEXT NOT NULL,                         -- min, pct
    base_legal  TEXT NOT NULL,
    UNIQUE (perfil, parametro)
);

INSERT INTO perfil_jornada (perfil, parametro, valor, unidade, base_legal) VALUES
    ('clt_padrao', 'jornada_diaria_min',           480,  'min', 'CF art. 7º, XIII; CLT art. 58'),
    ('clt_padrao', 'jornada_semanal_min',          2640, 'min', 'CF art. 7º, XIII; CLT art. 58'),
    ('clt_padrao', 'tolerancia_marcacao_min',      5,    'min', 'CLT art. 58, § 1º'),
    ('clt_padrao', 'tolerancia_dia_min',           10,   'min', 'CLT art. 58, § 1º'),
    ('clt_padrao', 'extras_max_dia_min',           120,  'min', 'CLT art. 59'),
    ('clt_padrao', 'adicional_extra_pct',          50,   'pct', 'CF art. 7º, XVI'),
    ('clt_padrao', 'interjornada_min',             660,  'min', 'CLT art. 66'),
    ('clt_padrao', 'descanso_semanal_min',         1440, 'min', 'CLT art. 67'),
    ('clt_padrao', 'intervalo_longo_acima_min',    360,  'min', 'CLT art. 71'),
    ('clt_padrao', 'intervalo_longo_min',          60,   'min', 'CLT art. 71'),
    ('clt_padrao', 'intervalo_curto_acima_min',    240,  'min', 'CLT art. 71, § 1º'),
    ('clt_padrao', 'intervalo_curto_min',          15,   'min', 'CLT art. 71, § 1º'),
    ('clt_padrao', 'noturno_inicio_min',           1320, 'min', 'CLT art. 73, § 2º'),
    ('clt_padrao', 'noturno_fim_min',              300,  'min', 'CLT art. 73, § 2º'),
    ('clt_padrao', 'hora_noturna_min',             52.5, 'min', 'CLT art. 73, § 1º'),
    ('clt_padrao', 'adicional_noturno_pct',        20,   'pct', 'CLT art. 73');

-- Resultado da análise de risco da folha de ponto (Goal 6): uma linha por documento; reprocessar substitui.
CREATE TABLE analise_ponto (
    documento_id    BIGINT PRIMARY KEY REFERENCES documento(id) ON DELETE CASCADE,
    estado          TEXT NOT NULL CHECK (estado IN ('concluida', 'erro')),
    erro            TEXT,
    perfil          JSONB,                             -- perfil de jornada usado (valor e base legal)
    marcacoes       JSONB,                             -- como extraídas pelo Gemini
    intervalo_pre_assinalado BOOLEAN,
    totais          JSONB,                             -- minutos apurados pelo código
    divergencias    JSONB,                             -- do código (valem estas)
    diferencas_gemini JSONB,                           -- onde o Gemini divergiu do código
    ponto_britanico JSONB,                             -- sinal de risco, não prova
    analise         TEXT,                              -- análise breve do Gemini (texto não confiável)
    contagens       JSONB,                             -- contagens calculadas pelo código e enviadas ao Jev
    scores_dimensao JSONB,                             -- por dimensão: score, n_niveis, confianca, probabilidades
    score_geral     DOUBLE PRECISION,                  -- máximo das dimensões normalizadas (0 a 1); NULL se nenhuma determinada
    requer_revisao  BOOLEAN NOT NULL DEFAULT false,    -- alguma dimensão indeterminada (não altera documento.estado)
    modelo_gemini   TEXT,
    modelo_jev      TEXT,
    versao_prompt_gemini TEXT,
    versao_prompt_jev TEXT,
    custo           JSONB,                             -- usage do Jev e do Gemini
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Campos extraídos de cada documento (Goal 7). Um valor por (documento, campo); upsert.
CREATE TABLE documento_campos (
    documento_id    BIGINT NOT NULL REFERENCES documento(id) ON DELETE CASCADE,
    campo           TEXT NOT NULL,
    valor           TEXT NOT NULL,
    origem          TEXT NOT NULL,                     -- quem gravou: modelo, humano, teste...
    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (documento_id, campo)
);
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(SCHEMA)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        DROP TABLE IF EXISTS documento_campos, analise_ponto, perfil_jornada, pagina, documento, lote, empresa CASCADE
        """
    )
