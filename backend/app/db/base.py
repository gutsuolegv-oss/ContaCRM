"""Baza modelelor și câmpurile comune."""

import enum
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Identity, MetaData, func
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
    # Valorile generate de bază (updated_at la UPDATE) se citesc imediat prin RETURNING.
    # Altfel ar rămâne expirate și s-ar încărca leneș, ceea ce în async nu merge.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012


def str_enum(enum_cls: type[enum.StrEnum], name: str, length: int = 16) -> Enum:
    """Enum salvat ca text (valorile, nu numele membrilor), cu constrângere CHECK în bază."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda e: [m.value for m in e],
    )


class IdMixin:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True, sort_order=-100)


# Câmpurile din mixin-uri apar în tabel după cele ale modelului (sort_order).
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), sort_order=100
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), sort_order=100
    )


class RecordStatus(enum.StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class SoftDeleteMixin:
    """Ștergere logică: rândul rămâne în bază, marcat `archived`, cu cine și când l-a arhivat."""

    status: Mapped[RecordStatus] = mapped_column(
        str_enum(RecordStatus, "status"),
        default=RecordStatus.ACTIVE,
        server_default=RecordStatus.ACTIVE.value,
        sort_order=100,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), sort_order=100)

    @declared_attr
    def deleted_by(cls) -> Mapped[int | None]:
        return mapped_column(
            BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), sort_order=100
        )
