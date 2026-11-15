"""Engine, sessão e dependência FastAPI do SQLAlchemy.

Módulo escolhido: `app/database.py`. Uso nos routers: `db: Session = Depends(get_session)`.
A engine só é criada na primeira sessão (nada conecta ao importar).
"""
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config


def url_sqlalchemy(url: str) -> str:
    """`postgresql://` e `postgres://` viram `postgresql+psycopg://` (driver psycopg v3)."""
    for prefixo in ("postgresql://", "postgres://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(url_sqlalchemy(config.DATABASE_URL), pool_pre_ping=True)


class _SessionLocal(sessionmaker):
    """sessionmaker que só resolve a engine ao criar a primeira sessão."""

    def __call__(self, **local_kw) -> Session:
        if self.kw.get("bind") is None and "bind" not in local_kw:
            local_kw["bind"] = get_engine()
        return super().__call__(**local_kw)


SessionLocal = _SessionLocal(autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """Dependência FastAPI: commit no sucesso, rollback na exceção, fecha sempre."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
