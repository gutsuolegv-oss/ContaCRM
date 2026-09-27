"""Baza modelelor și câmpurile comune."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# Nume stabile pentru constrângeri și indecși, ca migrările autogenerate să fie previzibile.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class RecordStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SoftDeleteMixin:
    """Ștergere logică: rândul rămâne în bază, marcat `archived`, cu cine și când l-a arhivat."""

    status: Mapped[RecordStatus] = mapped_column(
        Enum(
            RecordStatus,
            name="status",
            native_enum=False,
            create_constraint=True,
            length=16,
            values_callable=lambda e: [m.value for m in e],
        ),
        default=RecordStatus.ACTIVE,
        server_default=RecordStatus.ACTIVE.value,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @declared_attr
    def deleted_by(cls) -> Mapped[int | None]:
        return mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"))
