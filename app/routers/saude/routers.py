from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_session
from app.routers import r
from app.routers.saude.schemas import SaudeOut

router = APIRouter(tags=["Saúde"])


@router.get("/health", response_model=SaudeOut)
def health(session: Session = Depends(get_session)):
    session.execute(select(1))
    r.ping()
    return {"status": "ok"}
