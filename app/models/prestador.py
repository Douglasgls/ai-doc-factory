from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Text, text
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Prestador(Base):
    __tablename__ = "prestador"
    __table_args__ = (CheckConstraint("cnpj ~ '^[0-9]{14}$'", name="prestador_cnpj_check"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cnpj: Mapped[str] = mapped_column(CHAR(14), unique=True)
    razao_social: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    contratos: Mapped[list["Contrato"]] = relationship(back_populates="prestador")
