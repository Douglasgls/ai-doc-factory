from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Contrato(Base):
    __tablename__ = "contrato"
    __table_args__ = (
        UniqueConstraint("tomador_id", "prestador_id", name="contrato_tomador_id_prestador_id_key"),
        CheckConstraint("vigencia_fim >= vigencia_inicio", name="contrato_vigencia_check"),
        Index("contrato_prestador_idx", "prestador_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tomador_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tomador.id", ondelete="RESTRICT"))
    prestador_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("prestador.id", ondelete="RESTRICT"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    vigencia_fim: Mapped[date | None] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    tomador: Mapped["Tomador"] = relationship(back_populates="contratos")
    prestador: Mapped["Prestador"] = relationship(back_populates="contratos")
    lotes: Mapped[list["Lote"]] = relationship(back_populates="contrato")
