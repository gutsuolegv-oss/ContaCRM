from datetime import date

from sqlalchemy import Boolean, Date, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin


class Holiday(IdMixin, Base):
    """Zi nelucrătoare (sărbătoare) sau, cu `is_working`, zi lucrătoare recuperată
    (ex. o sâmbătă lucrată în locul unei zile de punte)."""

    __tablename__ = "holidays"

    holiday_date: Mapped[date] = mapped_column(Date, unique=True)
    name: Mapped[str] = mapped_column(String(200))
    is_working: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
