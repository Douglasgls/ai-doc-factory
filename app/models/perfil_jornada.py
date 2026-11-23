from datetime import date
from decimal import Decimal

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, ForeignKey, Index, Numeric, Text,
                        UniqueConstraint, text)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PerfilJornada(Base):
    """Uma linha por (perfil, parametro, vigente_desde). `vigente_desde` NULL é o valor de base (desde sempre); as
    demais linhas valem a partir da data. A resolução por data fica em app/ponto.py."""
    __tablename__ = "perfil_jornada"
    __table_args__ = (UniqueConstraint("perfil", "parametro", "vigente_desde",
                                       name="perfil_jornada_perfil_parametro_vigente_key",
                                       postgresql_nulls_not_distinct=True),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    perfil: Mapped[str] = mapped_column(Text)
    parametro: Mapped[str] = mapped_column(Text)
    valor: Mapped[Decimal] = mapped_column(Numeric)
    unidade: Mapped[str] = mapped_column(Text)
    base_legal: Mapped[str] = mapped_column(Text)
    vigente_desde: Mapped[date | None] = mapped_column(Date)


class PerfilJornadaCadastro(Base):
    """Uma linha por perfil: nome legível, sindicato e vigência. A chave é o slug de `perfil_jornada.perfil`."""
    __tablename__ = "perfil_jornada_cadastro"
    __table_args__ = (
        CheckConstraint("btrim(nome) <> ''", name="perfil_jornada_cadastro_nome_check"),
        CheckConstraint("vigencia_inicio IS NULL OR vigencia_fim IS NULL OR vigencia_fim >= vigencia_inicio",
                        name="perfil_jornada_cadastro_vigencia_check"),
        Index("perfil_jornada_cadastro_prestador_idx", "prestador_id"))

    perfil: Mapped[str] = mapped_column(Text, primary_key=True)
    nome: Mapped[str] = mapped_column(Text)
    sindicato: Mapped[str | None] = mapped_column(Text)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date)
    vigencia_fim: Mapped[date | None] = mapped_column(Date)
    # Escopo: o Padrão não usa estas colunas. Perfil geral = visível a todos que leem perfis; prestador_id = dono.
    geral: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    prestador_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("prestador.id", ondelete="SET NULL"))
