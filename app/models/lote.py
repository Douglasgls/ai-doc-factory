from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Lote(Base):
    __tablename__ = "lote"
    __table_args__ = (
        CheckConstraint("estado IN ('recebido', 'ocr', 'classificando', 'concluido', 'erro')", name="lote_estado_check"),
        CheckConstraint("docs_pendentes >= 0", name="lote_docs_pendentes_check"),
        Index("lote_contrato_idx", "contrato_id"),
        Index("lote_contrato_sha256_uniq", "contrato_id", "sha256", unique=True,
              postgresql_where=text("contrato_id IS NOT NULL")),
        Index("lote_sem_contrato_sha256_uniq", "sha256", unique=True,
              postgresql_where=text("contrato_id IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sha256: Mapped[str] = mapped_column(CHAR(64))
    nome_arquivo: Mapped[str] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(Text, server_default="recebido")
    docs_pendentes: Mapped[int] = mapped_column(Integer, server_default="0")
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    contrato_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("contrato.id", ondelete="RESTRICT"))

    contrato: Mapped["Contrato | None"] = relationship(back_populates="lotes")
    documentos: Mapped[list["Documento"]] = relationship(back_populates="lote", order_by="Documento.ordem")
    paginas: Mapped[list["Pagina"]] = relationship(back_populates="lote", order_by="Pagina.numero")
