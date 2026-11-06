"""Configuração única: tipos documentais, limiares e conexões (tudo vindo do ambiente)."""
import os

# Fonte única dos tipos documentais: slug -> rótulo e ícone (usado por GET /tipos). A ordem é a de exibição.
# Para adicionar um tipo, basta uma entrada aqui. Ícones aceitos: car, hash, idcard, home, file, briefcase.
TIPOS_INFO = {
    "aso": {"nome": "ASO (Atestado de Saúde Ocupacional)", "icone": "file"},
    "folha_pagamento": {"nome": "Folha de pagamento", "icone": "briefcase"},
    "folha_ponto": {"nome": "Folha de ponto", "icone": "hash"},
    "holerite": {"nome": "Holerite", "icone": "idcard"},
    "recibo_ferias": {"nome": "Recibo de férias", "icone": "home"},
    "atestado_medico": {"nome": "Atestado médico", "icone": "file"},
    "contrato_trabalho": {"nome": "Contrato de trabalho", "icone": "briefcase"},
}
TIPOS = tuple(TIPOS_INFO)

# Tipo atribuído quando a confiança fica abaixo de CONF_MIN. Fica fora de TIPOS de propósito:
# não é uma classe válida para a correção humana.
TIPO_DESCONHECIDO = "desconhecido"

CONF_AUTO = float(os.getenv("CONF_AUTO", "0.85"))
CONF_MIN = float(os.getenv("CONF_MIN", "0.50"))

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://docfactory:docfactory@localhost:5432/docfactory")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
DATA_DIR = os.getenv("DATA_DIR", "/data")

FILA_SEGMENTAR = "segmentar_lote"
FILA_CLASSIFICAR = "classificar_documento"
FILA_ANALISAR = "analisar_folha_ponto"
FILA_EXTRAIR = "extrair_campos"  # Goal 7: fora do fan-in do lote
MAX_TENTATIVAS = 3

# Segmentação: similaridade TF-IDF (cosseno) entre páginas consecutivas.
# Abaixo de SEG_SIM_BAIXO abre documento; a partir de SEG_SIM_ALTO continua; entre os dois é ambíguo.
# Valores iniciais NÃO calibrados com dados do gerador: ajustar depois com scripts/avaliar_segmentacao.py.
SEG_SIM_BAIXO = float(os.getenv("SEG_SIM_BAIXO", "0.15"))
SEG_SIM_ALTO = float(os.getenv("SEG_SIM_ALTO", "0.60"))
# Página com até este número de caracteres alfanuméricos (e sem "Página k de N") conta como branca: cobre o
# verso com só um carimbo ("PROTOCOLADO" = 11). Valor tirado do lote de ajuste L0001: NÃO calibrado.
SEG_BRANCO_MAX_ALNUM = int(os.getenv("SEG_BRANCO_MAX_ALNUM", "12"))

# Fronteira ambígua (Goal 1, passo 3): resposta do Jev (probabilidade de "mesmo documento") decidida em código.
# Valores iniciais NÃO calibrados.
SEG_LLM_CONTINUA = float(os.getenv("SEG_LLM_CONTINUA", "0.70"))  # >= : continua o documento
SEG_LLM_ABRE = float(os.getenv("SEG_LLM_ABRE", "0.30"))  # <= : abre documento novo; no meio, fica ambíguo

# LLMs. As chaves vêm só do ambiente (.env); nunca são gravadas em cache, log ou banco.
CLASSIFICADOR = os.getenv("CLASSIFICADOR", "jev")  # "jev" (Jev + Gemini) ou "regras" (sem rede)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
JEV_MODEL = os.getenv("JEV_MODEL", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
CACHE_DIR = os.getenv("CACHE_DIR", "/cache")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
LLM_TENTATIVAS = int(os.getenv("LLM_TENTATIVAS", "4"))
LLM_ESPERA = float(os.getenv("LLM_ESPERA", "1.5"))  # segundos; dobra a cada nova tentativa

# Análise de folha de ponto (Goal 6). O modelo realmente servido é lido de modelVersion e gravado em analise_ponto.
GEMINI_ANALISE_MODEL = os.getenv("GEMINI_ANALISE_MODEL", "gemini-3.5-flash")
PONTO_MAX_PAGINAS = int(os.getenv("PONTO_MAX_PAGINAS", "6"))  # páginas (imagens) enviadas ao Gemini
PONTO_TEXTO_MAX = int(os.getenv("PONTO_TEXTO_MAX", "20000"))  # caracteres de OCR enviados

# CORS: origens permitidas, separadas por vírgula (padrão: dev server do Vite). Nunca "*" com credenciais.
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://[::1]:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if o.strip()
]
