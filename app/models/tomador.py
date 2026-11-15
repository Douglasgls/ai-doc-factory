from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Tomador(Base):
    __tablename__ = "tomador"
    __table_args__ = (
        CheckConstraint("cnpj ~ '^[0-9]{14}$'", name="tomador_cnpj_check"),
        Index("tomador_nome_uniq", text("lower(btrim(nome))"), unique=True),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    nome: Mapped[str] = mapped_column(Text)
    cnpj: Mapped[str | None] = mapped_column(CHAR(14), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    contratos: Mapped[list["Contrato"]] = relationship(back_populates="tomador")
