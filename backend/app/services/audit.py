"""Jurnalul de modificări (audit_log): cine, ce, când, valorile vechi și noi."""

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.models import AuditAction, AuditLog, User

# created_at / updated_at: se schimbă la orice scriere, nu spun ce s-a modificat.
# password_hash: nu ajunge niciodată în jurnal (în audit se vede schimbarea parolei prin
# session_version / must_change_password).
_IGNORED = {"created_at", "updated_at", "password_hash"}


def _json(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def snapshot(obj: Base) -> dict[str, Any]:
    """Valorile coloanelor, în formă JSON."""
    return {
        attr.key: _json(getattr(obj, attr.key))
        for attr in inspect(obj).mapper.column_attrs
        if attr.key not in _IGNORED
    }


class AuditService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        self.session = session
        self.actor_id = actor.id if actor is not None else None

    def _add(
        self,
        action: AuditAction,
        obj: Base,
        old: dict[str, Any] | None,
        new: dict[str, Any] | None,
    ) -> None:
        self.session.add(
            AuditLog(
                user_id=self.actor_id,
                action=action,
                entity_type=obj.__tablename__,
                entity_id=obj.id,  # type: ignore[attr-defined]
                old_values=old,
                new_values=new,
            )
        )

    def created(self, obj: Base) -> None:
        self._add(AuditAction.CREATE, obj, None, snapshot(obj))

    def deleted(self, obj: Base, before: dict[str, Any]) -> None:
        """Ștergere, cu valorile luate înainte (după ștergere obiectul nu mai e în bază)."""
        self._add(AuditAction.DELETE, obj, before, None)

    def changed(
        self, obj: Base, before: dict[str, Any], action: AuditAction = AuditAction.UPDATE
    ) -> None:
        """Doar câmpurile schimbate. Fără schimbări, nu se scrie nimic."""
        after = snapshot(obj)
        keys = [k for k in after if after[k] != before.get(k)]
        if keys:
            self._add(action, obj, {k: before.get(k) for k in keys}, {k: after[k] for k in keys})
