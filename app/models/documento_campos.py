from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class DocumentoCampo(Base):
    __tablename__ = "documento_campos"

    documento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documento.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    campo: Mapped[str] = mapped_column(Text, primary_key=True)
    valor: Mapped[str] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(Text)
    autor: Mapped[str | None] = mapped_column(Text)  # e-mail de quem corrigiu (origem "humano"); NULL na extração
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    documento: Mapped["Documento"] = relationship(back_populates="campos")
