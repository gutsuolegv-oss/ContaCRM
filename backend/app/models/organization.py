from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    """Biroul de contabilitate care folosește CRM-ul (un singur rând). Datele lui se
    modifică din pagina „Setări” și apar în aplicație (bara laterală, documente)."""

    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint(r"idno IS NULL OR idno ~ '^[0-9]{13}$'", name="idno_format"),
        CheckConstraint(r"vat_code IS NULL OR vat_code ~ '^[0-9]{7}$'", name="vat_code_format"),
        CheckConstraint(r"iban IS NULL OR iban ~ '^MD[0-9]{2}[A-Z0-9]{20}$'", name="iban_format"),
    )

    name: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(500))  # denumirea juridică completă
    idno: Mapped[str | None] = mapped_column(String(13), unique=True)  # cod fiscal
    vat_code: Mapped[str | None] = mapped_column(String(7))
    legal_address: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(255))
    director_name: Mapped[str | None] = mapped_column(String(255))
    bank_name: Mapped[str | None] = mapped_column(String(100))
    iban: Mapped[str | None] = mapped_column(String(24))
