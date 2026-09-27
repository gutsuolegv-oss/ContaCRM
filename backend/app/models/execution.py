"""Nivelul 4: execuția — grila pe client, raport și perioadă, cu statusul fiecărei etape."""

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, str_enum


class PeriodType(enum.StrEnum):
    LUNAR = "lunar"
    TRIMESTRIAL = "trimestrial"
    SEMESTRIAL = "semestrial"
    ANUAL = "anual"


class ReportPeriod(IdMixin, TimestampMixin, Base):
    __tablename__ = "report_periods"
    __table_args__ = (
        UniqueConstraint("period_type", "year", "period_no"),
        CheckConstraint("end_date >= start_date", name="date_range"),
        CheckConstraint(
            "(period_type = 'lunar' AND period_no BETWEEN 1 AND 12) OR "
            "(period_type = 'trimestrial' AND period_no BETWEEN 1 AND 4) OR "
            "(period_type = 'semestrial' AND period_no BETWEEN 1 AND 2) OR "
            "(period_type = 'anual' AND period_no = 1)",
            name="period_no_range",
        ),
    )

    period_type: Mapped[PeriodType] = mapped_column(str_enum(PeriodType, "period_type", 20))
    year: Mapped[int] = mapped_column(Integer)
    period_no: Mapped[int] = mapped_column(Integer)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    is_closed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ReportEntry(IdMixin, TimestampMixin, Base):
    """O celulă din grilă: raportul X al clientului Y pentru perioada Z."""

    __tablename__ = "report_entries"
    __table_args__ = (
        UniqueConstraint("client_id", "report_type_id", "period_id"),
        CheckConstraint("is_completed = (completed_at IS NOT NULL)", name="completed_at_set"),
        Index(
            "ix_report_entries_open_deadline",
            "deadline",
            postgresql_where=text("NOT is_completed"),
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT")
    )
    report_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_types.id", ondelete="RESTRICT"), index=True
    )
    period_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_periods.id", ondelete="RESTRICT"), index=True
    )
    deadline: Mapped[date | None] = mapped_column(Date)  # gol pentru deadline_rule = manual
    assigned_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    is_completed: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class ReportEntryStep(IdMixin, Base):
    """Statusul curent al unei etape. Că statusul aparține setului etapei verifică serviciul."""

    __tablename__ = "report_entry_steps"
    __table_args__ = (UniqueConstraint("entry_id", "step_id"),)

    entry_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_entries.id", ondelete="CASCADE")
    )
    step_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_type_steps.id", ondelete="RESTRICT"), index=True
    )
    status_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("statuses.id", ondelete="RESTRICT"), index=True
    )
    changed_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
