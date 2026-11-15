from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class AnalisePonto(Base):
    __tablename__ = "analise_ponto"
    __table_args__ = (CheckConstraint("estado IN ('concluida', 'erro')", name="analise_ponto_estado_check"),)

    documento_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("documento.id", ondelete="CASCADE"), primary_key=True, autoincrement=False
    )
    estado: Mapped[str] = mapped_column(Text)
    erro: Mapped[str | None] = mapped_column(Text)
    perfil: Mapped[dict | None] = mapped_column(JSONB)
    marcacoes: Mapped[dict | None] = mapped_column(JSONB)
    intervalo_pre_assinalado: Mapped[bool | None] = mapped_column(Boolean)
    totais: Mapped[dict | None] = mapped_column(JSONB)
    divergencias: Mapped[dict | None] = mapped_column(JSONB)
    diferencas_gemini: Mapped[dict | None] = mapped_column(JSONB)
    ponto_britanico: Mapped[dict | None] = mapped_column(JSONB)
    analise: Mapped[str | None] = mapped_column(Text)
    contagens: Mapped[dict | None] = mapped_column(JSONB)
    scores_dimensao: Mapped[dict | None] = mapped_column(JSONB)
    score_geral: Mapped[float | None] = mapped_column(Float)
    requer_revisao: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    modelo_gemini: Mapped[str | None] = mapped_column(Text)
    modelo_jev: Mapped[str | None] = mapped_column(Text)
    versao_prompt_gemini: Mapped[str | None] = mapped_column(Text)
    versao_prompt_jev: Mapped[str | None] = mapped_column(Text)
    custo: Mapped[dict | None] = mapped_column(JSONB)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

    documento: Mapped["Documento"] = relationship(back_populates="analise_ponto")
