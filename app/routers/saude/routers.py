import psycopg
from fastapi import APIRouter

from app import config
from app.routers import r
from app.routers.saude.schemas import SaudeOut

router = APIRouter(tags=["Saúde"])


@router.get("/health", response_model=SaudeOut)
def health():
    with psycopg.connect(config.DATABASE_URL) as conn:
        conn.execute("SELECT 1")
    r.ping()
    return {"status": "ok"}
