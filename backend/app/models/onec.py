"""Integrarea cu 1C: soldurile clienților față de birou, trimise de scriptul de pe
calculatorul cu 1C (infra/onec). Doar admin și director văd aceste date.

Fiecare trimitere e o sincronizare (`onec_sync_runs`); soldurile potrivite după IDNO cu
clienții din CRM se păstrează pe sincronizare (istoric), iar contragenții negăsiți rămân
în `unmatched`, ca adminul să-i poată verifica.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class OneCIntegration(IdMixin, TimestampMixin, Base):
    """Cheia cu care scriptul din 1C trimite datele (un singur rând). Se păstrează doar
    hash-ul cheii; cheia întreagă se arată o singură dată, la generare."""

    __tablename__ = "onec_integration"

    api_key_hash: Mapped[str | None] = mapped_column(String(64), unique=True)  # SHA-256, hex
    api_key_hint: Mapped[str | None] = mapped_column(String(12))  # ultimele caractere
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )


class OneCSyncRun(IdMixin, Base):
    """O trimitere a scriptului: soldurile la data `as_of`."""

    __tablename__ = "onec_sync_runs"

    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    as_of: Mapped[date] = mapped_column(Date)
    base_name: Mapped[str | None] = mapped_column(String(255))  # numele bazei 1C
    script_version: Mapped[str | None] = mapped_column(String(32))
    rows: Mapped[int] = mapped_column(Integer)  # contragenți primiți
    matched: Mapped[int] = mapped_column(Integer)  # potriviți cu clienți din CRM
    total_debit: Mapped[Decimal] = mapped_column(Numeric(16, 2))  # la clienții potriviți
    # [{"idno", "name", "debit", "credit"}] - contragenții din 1C negăsiți în CRM
    unmatched: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)


class ClientBalance(IdMixin, Base):
    """Soldul unui client la o sincronizare: `debit` = cât datorează biroului,
    `credit` = avans (plătit în plus)."""

    __tablename__ = "client_balances"
    __table_args__ = (
        UniqueConstraint("run_id", "client_id"),
        Index("ix_client_balances_client_run", "client_id", "run_id"),
    )

    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("onec_sync_runs.id", ondelete="CASCADE")
    )
    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT")
    )
    debit: Mapped[Decimal] = mapped_column(Numeric(16, 2))
    credit: Mapped[Decimal] = mapped_column(Numeric(16, 2))
