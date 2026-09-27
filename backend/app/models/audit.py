import enum
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, str_enum


class AuditAction(enum.StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    RETIRE = "retire"


class AuditLog(IdMixin, Base):
    """Jurnal de modificări: cine, ce, când, valorile vechi și noi. Doar se adaugă rânduri."""

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_entity", "entity_type", "entity_id"),)

    user_id: Mapped[int | None] = mapped_column(  # gol pentru acțiunile sistemului
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[AuditAction] = mapped_column(str_enum(AuditAction, "action", 20))
    entity_type: Mapped[str] = mapped_column(String(50))  # numele tabelului
    entity_id: Mapped[int] = mapped_column(BigInteger)
    old_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_values: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
