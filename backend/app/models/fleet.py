"""Parc auto: automobilele clienților, odometrul la sfârșitul fiecărei luni și foile de parcurs.

Odometrul de început al unei luni nu se salvează: e odometrul de sfârșit al lunii anterioare
cu date sau, pentru prima lună, `vehicles.initial_odometer`. Foaia de parcurs păstrează însă
toate valorile din momentul emiterii, ca să nu se schimbe dacă se modifică ulterior
automobilul (norma, șoferul) sau citirile.
"""

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, str_enum


class FuelType(enum.StrEnum):
    BENZINA = "benzina"
    MOTORINA = "motorina"
    GPL = "gpl"
    HIBRID = "hibrid"


class ReadingSource(enum.StrEnum):
    """Cum a transmis clientul odometrul (Telegram: când va exista gateway-ul)."""

    EMAIL = "email"
    PHONE = "phone"
    TELEGRAM = "telegram"
    OTHER = "other"


class Vehicle(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint(r"plate ~ '^[A-Z0-9 -]{2,15}$'", name="plate_format"),
        CheckConstraint("fuel_norm > 0", name="fuel_norm_positive"),
        CheckConstraint("initial_odometer >= 0", name="initial_odometer_positive"),
        # Un număr de înmatriculare e la un singur client la un moment dat.
        Index(
            "uq_vehicles_plate_active",
            "plate",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    plate: Mapped[str] = mapped_column(String(15))  # majuscule, ex. „CDK 540”
    model: Mapped[str] = mapped_column(String(100))
    fuel_type: Mapped[FuelType] = mapped_column(str_enum(FuelType, "fuel_type"))
    fuel_norm: Mapped[Decimal] = mapped_column(Numeric(5, 2))  # litri / 100 km
    driver: Mapped[str | None] = mapped_column(String(255))
    initial_odometer: Mapped[int] = mapped_column(Integer)  # km, la luarea în evidență


class OdometerReading(IdMixin, TimestampMixin, Base):
    """Odometrul la sfârșitul lunii `year`/`month`."""

    __tablename__ = "odometer_readings"
    __table_args__ = (
        UniqueConstraint("vehicle_id", "year", "month"),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
        CheckConstraint("end_odometer >= 0", name="end_odometer_positive"),
    )

    vehicle_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("vehicles.id", ondelete="RESTRICT"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    end_odometer: Mapped[int] = mapped_column(Integer)
    source: Mapped[ReadingSource] = mapped_column(str_enum(ReadingSource, "reading_source"))
    received_on: Mapped[date] = mapped_column(Date)
    entered_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )

    waybill: Mapped["Waybill | None"] = relationship(back_populates="reading", lazy="raise")


class Waybill(IdMixin, Base):
    """Foaia de parcurs pe o lună, cu valorile de la emitere."""

    __tablename__ = "waybills"
    __table_args__ = (CheckConstraint("end_odometer >= start_odometer", name="odometer_order"),)

    reading_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("odometer_readings.id", ondelete="RESTRICT"), unique=True
    )
    number: Mapped[str] = mapped_column(String(30), unique=True)  # FP-2026-09-001
    plate: Mapped[str] = mapped_column(String(15))
    model: Mapped[str] = mapped_column(String(100))
    fuel_type: Mapped[FuelType] = mapped_column(str_enum(FuelType, "fuel_type"))
    driver: Mapped[str | None] = mapped_column(String(255))
    fuel_norm: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    start_odometer: Mapped[int] = mapped_column(Integer)
    end_odometer: Mapped[int] = mapped_column(Integer)
    fuel_liters: Mapped[Decimal] = mapped_column(Numeric(9, 2))
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    issued_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )

    reading: Mapped[OdometerReading] = relationship(back_populates="waybill", lazy="raise")
