from decimal import Decimal

from sqlalchemy import BigInteger, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PerfilJornada(Base):
    __tablename__ = "perfil_jornada"
    __table_args__ = (UniqueConstraint("perfil", "parametro", name="perfil_jornada_perfil_parametro_key"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    perfil: Mapped[str] = mapped_column(Text)
    parametro: Mapped[str] = mapped_column(Text)
    valor: Mapped[Decimal] = mapped_column(Numeric)
    unidade: Mapped[str] = mapped_column(Text)
    base_legal: Mapped[str] = mapped_column(Text)
