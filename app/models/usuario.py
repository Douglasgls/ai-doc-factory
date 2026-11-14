from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        CheckConstraint("nivel IN ('plataforma', 'tomador', 'prestador')", name="usuario_nivel_check"),
        CheckConstraint("papel IN ('admin', 'membro')", name="usuario_papel_check"),
        CheckConstraint(
            "(nivel = 'plataforma' AND tomador_id IS NULL     AND prestador_id IS NULL) OR "
            "(nivel = 'tomador'    AND tomador_id IS NOT NULL AND prestador_id IS NULL) OR "
            "(nivel = 'prestador'  AND prestador_id IS NOT NULL AND tomador_id IS NULL)",
            name="usuario_nivel_vinculo_check",
        ),
        Index("usuario_email_uniq", text("lower(email)"), unique=True),
        Index("usuario_tomador_idx", "tomador_id"),
        Index("usuario_prestador_idx", "prestador_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(Text)
    nome: Mapped[str] = mapped_column(Text)
    senha_hash: Mapped[str | None] = mapped_column(Text)
    nivel: Mapped[str] = mapped_column(Text)
    papel: Mapped[str] = mapped_column(Text)
    tomador_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tomador.id", ondelete="RESTRICT"))
    prestador_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("prestador.id", ondelete="RESTRICT"))
    ativo: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
