from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import CHAR
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Convite(Base):
    __tablename__ = "convite"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="convite_token_hash_check"),
        CheckConstraint("nivel IN ('plataforma', 'tomador', 'prestador')", name="convite_nivel_check"),
        CheckConstraint("papel IN ('admin', 'membro')", name="convite_papel_check"),
        CheckConstraint(
            "(nivel = 'plataforma' AND tomador_id IS NULL     AND prestador_id IS NULL) OR "
            "(nivel = 'tomador'    AND tomador_id IS NOT NULL AND prestador_id IS NULL) OR "
            "(nivel = 'prestador'  AND prestador_id IS NOT NULL AND tomador_id IS NULL)",
            name="convite_nivel_vinculo_check",
        ),
        Index("convite_token_hash_uniq", "token_hash", unique=True),
        Index("convite_email_idx", text("lower(email)")),
        Index("convite_tomador_idx", "tomador_id"),
        Index("convite_prestador_idx", "prestador_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    token_hash: Mapped[str] = mapped_column(CHAR(64))
    email: Mapped[str] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text)
    papel: Mapped[str] = mapped_column(Text)
    tomador_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tomador.id", ondelete="RESTRICT"))
    prestador_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("prestador.id", ondelete="RESTRICT"))
    criado_por: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    usuario_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usuario.id", ondelete="SET NULL"))
