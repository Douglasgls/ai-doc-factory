from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Documento(Base):
    __tablename__ = "documento"
    __table_args__ = (
        CheckConstraint(
            "estado IN ('segmentado', 'classificado', 'em_revisao', 'revisado', 'erro')", name="documento_estado_check"
        ),
        CheckConstraint("pagina_fim >= pagina_ini", name="documento_check"),
        UniqueConstraint("lote_id", "ordem", name="documento_lote_id_ordem_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("lote.id", ondelete="CASCADE"))
    ordem: Mapped[int] = mapped_column(Integer)
    pagina_ini: Mapped[int] = mapped_column(Integer)
    pagina_fim: Mapped[int] = mapped_column(Integer)
    estado: Mapped[str] = mapped_column(Text, server_default="segmentado")
    tipo: Mapped[str | None] = mapped_column(Text)
    confianca: Mapped[float | None] = mapped_column(Float)
    tipo_original: Mapped[str | None] = mapped_column(Text)
    revisor: Mapped[str | None] = mapped_column(Text)
    revisado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    motivo_revisao: Mapped[str | None] = mapped_column(Text)
    modelo: Mapped[str | None] = mapped_column(Text)
    versao_prompt: Mapped[str | None] = mapped_column(Text)
    probabilidades: Mapped[dict | None] = mapped_column(JSONB)
    segunda_opiniao: Mapped[dict | None] = mapped_column(JSONB)
    segmentacao_ambigua: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    nome_padronizado: Mapped[str | None] = mapped_column(Text)

    lote: Mapped["Lote"] = relationship(back_populates="documentos")
    paginas: Mapped[list["Pagina"]] = relationship(back_populates="documento", order_by="Pagina.numero")
    campos: Mapped[list["DocumentoCampo"]] = relationship(back_populates="documento")
    analise_ponto: Mapped["AnalisePonto | None"] = relationship(back_populates="documento", uselist=False)
