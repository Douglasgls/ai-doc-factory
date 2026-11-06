from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config
from app.routers import r  # noqa: F401  (reexportado: conexão Redis compartilhada)
from app.routers.auth.actions import exigir_usuario
from app.routers.auth.routers import router as auth
from app.routers.busca.routers import router as busca
from app.routers.cadastro_empresas.routers import router as cadastro_empresas
from app.routers.documentos.routers import router as documentos
from app.routers.empresas.routers import router as empresas
from app.routers.lotes.routers import router as lotes
from app.routers.revisao.routers import router as revisao
from app.routers.saude.routers import router as saude
from app.routers.tipos.routers import router as tipos

app = FastAPI(title="Document AI Factory")
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Abertas: /health (healthcheck do compose) e /auth/login. Todo o resto exige token.
# /auth/me se protege sozinha. Router novo entra na tupla protegida: o teste de varredura cobra isso.
app.include_router(saude)
app.include_router(auth)
for router in (lotes, busca, documentos, revisao, empresas, cadastro_empresas, tipos):
    app.include_router(router, dependencies=[Depends(exigir_usuario)])
