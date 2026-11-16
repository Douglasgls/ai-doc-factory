from datetime import date
from decimal import Decimal

from sqlalchemy import BigInteger, Date, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PerfilJornada(Base):
    """Uma linha por (perfil, parametro, vigente_desde). `vigente_desde` NULL é o valor de base (desde sempre); as
    demais linhas valem a partir da data. A resolução por data fica em app/ponto.py."""
    __tablename__ = "perfil_jornada"
    __table_args__ = (UniqueConstraint("perfil", "parametro", "vigente_desde",
                                       name="perfil_jornada_perfil_parametro_vigente_key",
                                       postgresql_nulls_not_distinct=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    perfil: Mapped[str] = mapped_column(Text)
    parametro: Mapped[str] = mapped_column(Text)
    valor: Mapped[Decimal] = mapped_column(Numeric)
    unidade: Mapped[str] = mapped_column(Text)
    base_legal: Mapped[str] = mapped_column(Text)
    vigente_desde: Mapped[date | None] = mapped_column(Date)
