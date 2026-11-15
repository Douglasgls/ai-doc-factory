"""Base declarativa de todos os modelos. O schema real vem das migrações Alembic (migrations/versions);
os modelos apenas o refletem."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
