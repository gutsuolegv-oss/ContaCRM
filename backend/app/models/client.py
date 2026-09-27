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
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, SoftDeleteMixin, TimestampMixin, str_enum


class LegalForm(enum.StrEnum):
    SRL = "SRL"
    SA = "SA"
    II = "II"  # Întreprindere Individuală
    GT = "GT"  # Gospodărie Țărănească
    ONG = "ONG"


class ClientStatus(enum.StrEnum):
    """Etapa clientului; separat de `status` (ștergerea logică)."""

    ONBOARDING = "onboarding"
    ACTIVE = "active"


class Client(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "clients"
    __table_args__ = (
        CheckConstraint(r"idno ~ '^[0-9]{13}$'", name="idno_format"),
        CheckConstraint(
            r"vat_code IS NULL OR (vat_payer AND vat_code ~ '^[0-9]{7}$')", name="vat_code"
        ),
        Index(
            "uq_clients_idno_active",
            "idno",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(500))
    idno: Mapped[str] = mapped_column(String(13))
    legal_form: Mapped[LegalForm] = mapped_column(str_enum(LegalForm, "legal_form"))
    vat_payer: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    vat_code: Mapped[str | None] = mapped_column(String(7))
    locality: Mapped[str | None] = mapped_column(String(100))
    legal_address: Mapped[str | None] = mapped_column(String(500))
    caem_code: Mapped[str | None] = mapped_column(String(10))
    activity: Mapped[str | None] = mapped_column(String(255))
    registered_on: Mapped[date | None] = mapped_column(Date)
    client_since: Mapped[date | None] = mapped_column(Date)
    client_status: Mapped[ClientStatus] = mapped_column(
        str_enum(ClientStatus, "client_status"),
        default=ClientStatus.ONBOARDING,
        server_default=ClientStatus.ONBOARDING.value,
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )


class ClientBankAccount(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "client_bank_accounts"
    __table_args__ = (
        CheckConstraint(r"iban ~ '^MD[0-9]{2}[A-Z0-9]{20}$'", name="iban_format"),
        CheckConstraint(r"currency ~ '^[A-Z]{3}$'", name="currency_format"),
        Index(
            "uq_client_bank_accounts_iban_active",
            "client_id",
            "iban",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        # Cel mult un cont principal per client.
        Index(
            "uq_client_bank_accounts_primary",
            "client_id",
            unique=True,
            postgresql_where=text("is_primary AND deleted_at IS NULL"),
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    bank_name: Mapped[str] = mapped_column(String(100))
    iban: Mapped[str] = mapped_column(String(24))  # fără spații, majuscule
    currency: Mapped[str] = mapped_column(String(3), server_default="MDL")
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))


class ClientContact(IdMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "client_contacts"
    __table_args__ = (
        # Cel mult un contact principal per client.
        Index(
            "uq_client_contacts_primary",
            "client_id",
            unique=True,
            postgresql_where=text("is_primary AND deleted_at IS NULL"),
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(100))  # „Administrator”, „Contabil intern”
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))


class ClientAssignment(IdMixin, Base):
    """Contabilii unui client. Rândul cu `unassigned_at` gol e o repartizare curentă;
    rândurile închise rămân ca istoric. Un client poate avea mai mulți contabili."""

    __tablename__ = "client_assignments"
    __table_args__ = (
        CheckConstraint(
            "unassigned_at IS NULL OR unassigned_at >= assigned_at", name="unassigned_after"
        ),
        Index(
            "uq_client_assignments_current",
            "client_id",
            "user_id",
            unique=True,
            postgresql_where=text("unassigned_at IS NULL"),
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    assigned_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    unassigned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unassigned_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
