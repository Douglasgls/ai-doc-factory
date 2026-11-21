import logging
import re

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.routers import r  # noqa: F401  (reexportado: conexão Redis compartilhada)
from app.escopo import acesso_a_dados
from app.routers.auth.actions import exigir_plataforma, exigir_usuario
from app.routers.auth.routers import router as auth
from app.routers.busca.routers import router as busca
from app.routers.convites.routers import router as convites
from app.routers.convites.routers import router_publico as convites_publico
from app.routers.documentos.routers import router as documentos
from app.routers.empresas.routers import router as empresas
from app.routers.lotes.routers import router as lotes
from app.routers.organizacoes.routers import router as organizacoes
from app.routers.organizacoes.routers import router_leitura as contratos_leitura
from app.routers.perfis_jornada.routers import router as perfis_jornada
from app.routers.revisao.routers import router as revisao
from app.routers.saude.routers import router as saude
from app.routers.terceirizadas.routers import router as terceirizadas
from app.routers.tipos.routers import router as tipos
from app.routers.usuarios.routers import router as usuarios



class _OcultarTokenDeConvite(logging.Filter):
    """O token de convite viaja no caminho (/convites/{token}[/aceitar]): não pode ir para o log de acesso."""
    _TOKEN = re.compile(r"(/convites/)[^/?\s]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._TOKEN.sub(r"\1***", a) if isinstance(a, str) else a for a in record.args)
        return True


logging.getLogger("uvicorn.access").addFilter(_OcultarTokenDeConvite())

app = FastAPI(title="Document AI Factory")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Abertas: /health (healthcheck do compose), /auth/login e as duas rotas por token de /convites/{token}. Todo o resto exige token.
# /auth/me se protege sozinha (qualquer usuário autenticado). Matriz de acesso (app/escopo.py):
#   - lotes, busca, documentos, revisao, empresas (conformidade), GET /contratos: qualquer nível, filtrado pelo escopo; tomador só lê;
#   - tipos: qualquer usuário logado;
#   - POST /terceirizadas (admin do tomador ou plataforma), GET /usuarios e GET /convites (admin da organização):
#     autenticadas, decididas na action; fora de acesso_a_dados de propósito (o admin do tomador escreve aqui);
#   - criação de tomador/prestador/contrato e perfis de jornada (cadastro e associação
#     ao contrato): só plataforma.
# Router novo SEM dependência fica aberto: a varredura de tests/test_autenticacao.py e tests/test_isolamento.py cobra isso.
app.include_router(saude)
app.include_router(auth)
app.include_router(convites_publico)  # GET /convites/{token} e POST /convites/{token}/aceitar: o token é a credencial
app.include_router(convites, dependencies=[Depends(exigir_usuario)])  # POST /convites: pode_convidar decide; GET /convites: escopo por organização (membro 403)
for router in (lotes, busca, documentos, revisao, contratos_leitura, empresas):
    app.include_router(router, dependencies=[Depends(acesso_a_dados)])
app.include_router(tipos, dependencies=[Depends(exigir_usuario)])
for router in (terceirizadas, usuarios):  # a action decide por nível e papel (admin do tomador / admin da organização)
    app.include_router(router, dependencies=[Depends(exigir_usuario)])
for router in (organizacoes, perfis_jornada):
    app.include_router(router, dependencies=[Depends(exigir_plataforma)])
