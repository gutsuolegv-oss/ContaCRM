"""Nivelul 3: matricea obligațiilor — ce rapoarte are de depus fiecare client."""

import enum
from datetime import date

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, str_enum


class ObligationSource(enum.StrEnum):
    AUTO = "auto"  # din motorul de reguli; recalcularea o poate dezactiva
    MANUAL = "manual"  # atribuită de om; recalcularea nu o atinge


class ClientReportType(IdMixin, TimestampMixin, Base):
    __tablename__ = "client_report_types"
    __table_args__ = (
        UniqueConstraint("client_id", "report_type_id", "valid_from"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        Index("ix_client_report_types_active", "client_id", postgresql_where=text("is_active")),
    )

    client_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("clients.id", ondelete="CASCADE"))
    report_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_types.id", ondelete="RESTRICT"), index=True
    )
    source: Mapped[ObligationSource] = mapped_column(str_enum(ObligationSource, "source", 20))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    valid_from: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    valid_to: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
