"""Nivelele 1 și 2 ale modulului de rapoarte: clasificatorul și regulile de aplicabilitate.

Clasificatorul nu folosește ștergerea logică din SoftDeleteMixin: o înregistrare se dezactivează
(`is_active`), iar un tip de raport se retrage cu `valid_to`. Cine și când a modificat se vede în
`audit_log`.
"""

import enum
from datetime import date
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, str_enum


class Periodicity(enum.StrEnum):
    LUNAR = "lunar"
    TRIMESTRIAL = "trimestrial"
    SEMESTRIAL = "semestrial"
    ANUAL = "anual"
    LA_CERERE = "la_cerere"


class DeadlineRule(enum.StrEnum):
    DAY_OF_NEXT_PERIOD = "day_of_next_period"  # ziua `deadline_day` după perioada de gestiune
    FIXED_DATE = "fixed_date"  # `deadline_day`.`deadline_month`
    MANUAL = "manual"  # fără termen calculat


class RuleAction(enum.StrEnum):
    ASSIGN = "assign"
    EXCLUDE = "exclude"


class ReportCategory(IdMixin, TimestampMixin, Base):
    __tablename__ = "report_categories"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))


class StatusSet(IdMixin, TimestampMixin, Base):
    """Set de statusuri pentru o etapă (ex. depunere: neinceput → transmis → incarcat)."""

    __tablename__ = "status_sets"

    code: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))


class Status(IdMixin, TimestampMixin, Base):
    __tablename__ = "statuses"
    __table_args__ = (
        UniqueConstraint("status_set_id", "code"),
        # Cel mult un status inițial per set.
        Index(
            "uq_statuses_initial",
            "status_set_id",
            unique=True,
            postgresql_where=text("is_initial"),
        ),
    )

    status_set_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("status_sets.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    is_initial: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    is_final: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))  # închide etapa
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ReportType(IdMixin, TimestampMixin, Base):
    """Un tip de raport, valabil în intervalul [valid_from, valid_to]. Nu se șterge niciodată:
    o versiune nouă a aceluiași cod primește alt `valid_from`."""

    __tablename__ = "report_types"
    __table_args__ = (
        UniqueConstraint("code", "valid_from"),
        CheckConstraint("valid_to IS NULL OR valid_to >= valid_from", name="valid_range"),
        CheckConstraint("deadline_day BETWEEN 1 AND 31", name="deadline_day_range"),
        CheckConstraint("deadline_month BETWEEN 1 AND 12", name="deadline_month_range"),
        CheckConstraint(
            "deadline_rule <> 'day_of_next_period' OR deadline_day IS NOT NULL",
            name="next_period_needs_day",
        ),
        CheckConstraint(
            "deadline_rule <> 'fixed_date' OR (deadline_day IS NOT NULL "
            "AND deadline_month IS NOT NULL)",
            name="fixed_date_needs_day_month",
        ),
    )

    category_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_categories.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(Text)
    legal_reference: Mapped[str | None] = mapped_column(Text)
    authority: Mapped[str | None] = mapped_column(String(100))
    periodicity: Mapped[Periodicity] = mapped_column(str_enum(Periodicity, "periodicity", 20))
    deadline_rule: Mapped[DeadlineRule] = mapped_column(str_enum(DeadlineRule, "deadline_rule", 30))
    deadline_day: Mapped[int | None] = mapped_column(Integer)
    deadline_month: Mapped[int | None] = mapped_column(Integer)
    requires_payment: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    notify_days_before: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), server_default=text("'{7,3,1}'")
    )
    valid_from: Mapped[date] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ReportTypeStep(IdMixin, TimestampMixin, Base):
    """Etapă a unui raport (ex. transmitere, înregistrare în 1C), cu setul ei de statusuri."""

    __tablename__ = "report_type_steps"
    __table_args__ = (UniqueConstraint("report_type_id", "code"),)

    report_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_types.id", ondelete="CASCADE")
    )
    status_set_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("status_sets.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    is_required: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, server_default=text("0"))


class ReportRule(IdMixin, TimestampMixin, Base):
    """Cui se aplică un raport. `conditions` e evaluat de motorul de reguli pe atributele
    clientului; `{}` înseamnă toți clienții."""

    __tablename__ = "report_rules"

    report_type_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("report_types.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    conditions: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'"))
    action: Mapped[RuleAction] = mapped_column(str_enum(RuleAction, "action", 20))
    priority: Mapped[int] = mapped_column(Integer, server_default=text("100"))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
