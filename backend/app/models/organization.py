from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin


class Organization(IdMixin, TimestampMixin, Base):
    """Biroul de contabilitate care folosește CRM-ul (un singur rând)."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255))
    idno: Mapped[str | None] = mapped_column(String(13), unique=True)  # cod fiscal
