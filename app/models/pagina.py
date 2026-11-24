from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, Integer, Text, UniqueConstraint, column, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Pagina(Base):
    __tablename__ = "pagina"
    __table_args__ = (
        UniqueConstraint("lote_id", "numero", name="pagina_lote_id_numero_key"),
        Index("pagina_documento_idx", "documento_id"),
        Index(
            "pagina_texto_fts_idx",
            func.to_tsvector("portuguese", func.coalesce(column("texto"), "")),
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lote.id", ondelete="CASCADE"))
    numero: Mapped[int] = mapped_column(Integer)
    documento_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("documento.id", ondelete="SET NULL"))
    texto: Mapped[str | None] = mapped_column(Text)
    texto_nativo: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))

    lote: Mapped["Lote"] = relationship(back_populates="paginas")
    documento: Mapped["Documento | None"] = relationship(back_populates="paginas")
