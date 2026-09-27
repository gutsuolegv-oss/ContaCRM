"""Conturile utilizatorilor. Le administrează doar adminul (directorul doar le vede).

- Parola inițială / resetată o setează adminul; utilizatorul trebuie s-o schimbe la prima
  logare (`must_change_password`).
- La schimbarea sau resetarea parolei și la arhivare, sesiunile existente se închid: refresh
  token-urile se revocă, iar access token-urile emise înainte sunt refuzate
  (`session_version` crește).
- Biroul nu rămâne fără admin: ultimul admin activ nu poate fi arhivat sau retrogradat.
  Nimeni nu își arhivează propriul cont.
- La arhivarea unui utilizator, repartizările lui la clienți se închid.
"""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.db.base import RecordStatus
from app.models import ClientAssignment, Organization, User, UserRole
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository
from app.schemas.users import PasswordChange, UserCreate, UserUpdate
from app.services.audit import AuditService, snapshot
from app.services.auth import AuthService, TokenPair
from app.services.classifier import apply_changes
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)

_USERNAME_CONFLICT = "Există deja un utilizator activ cu acest nume"


class UserService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    def _require_admin(self) -> None:
        if self.actor.role is not UserRole.ADMIN:
            raise ForbiddenError("Doar adminul administrează conturile")

    # --- Citire ---

    async def list(
        self, role: UserRole | None = None, include_archived: bool = False
    ) -> Sequence[User]:
        stmt = select(User).order_by(User.full_name, User.id)
        if role is not None:
            stmt = stmt.where(User.role == role)
        if not include_archived:
            stmt = stmt.where(User.status == RecordStatus.ACTIVE, User.deleted_at.is_(None))
        return (await self.session.scalars(stmt)).all()

    async def get(self, user_id: int) -> User:
        user = await self.session.get(User, user_id)
        if user is None:
            raise NotFoundError("Utilizatorul nu există")
        return user

    async def _get_active(self, user_id: int) -> User:
        user = await self.users.get_active(user_id)
        if user is None:
            raise NotFoundError("Utilizatorul nu există")
        return user

    # --- Administrare (admin) ---

    async def create(self, data: UserCreate) -> User:
        self._require_admin()
        user = User(
            organization_id=await self._organization_id(),
            username=data.username,
            full_name=data.full_name,
            role=data.role,
            password_hash=security.hash_password(data.password),
            must_change_password=True,
        )
        async with conflict_guard(self.session, _USERNAME_CONFLICT):
            self.users.add(user)
        self.audit.created(user)
        await self.session.commit()
        return user

    async def _organization_id(self) -> int:
        org_id = await self.session.scalar(select(func.min(Organization.id)))
        if org_id is None:
            raise ValidationFailedError("Organizația nu există (vezi python -m app.cli)")
        return org_id

    async def update(self, user_id: int, data: UserUpdate) -> User:
        self._require_admin()
        user = await self._get_active(user_id)
        values = data.model_dump(exclude_unset=True)
        new_role = values.get("role")
        if new_role is not None and new_role is not UserRole.ADMIN:
            await self._ensure_not_last_admin(user)
        before = snapshot(user)
        async with conflict_guard(self.session, _USERNAME_CONFLICT):
            apply_changes(user, values)
        self.audit.changed(user, before)
        await self.session.commit()
        return user

    async def reset_password(self, user_id: int, password: str, now: datetime) -> User:
        """Parolă nouă setată de admin; utilizatorul trebuie s-o schimbe la logare."""
        self._require_admin()
        user = await self._get_active(user_id)
        await self._set_password(user, password, now, must_change=True)
        await self.session.commit()
        return user

    async def archive(self, user_id: int, now: datetime) -> User:
        self._require_admin()
        user = await self._get_active(user_id)
        if user.id == self.actor.id:
            raise ConflictError("Nu îți poți arhiva propriul cont")
        await self._ensure_not_last_admin(user)

        before = snapshot(user)
        async with conflict_guard(self.session, "Utilizatorul nu a putut fi arhivat"):
            user.status = RecordStatus.ARCHIVED
            user.deleted_at = now
            user.deleted_by = self.actor.id
            user.session_version += 1
        self.audit.changed(user, before)
        await self.tokens.revoke_all_for_user(user.id, now)

        open_assignments = await self.session.scalars(
            select(ClientAssignment).where(
                ClientAssignment.user_id == user.id, ClientAssignment.unassigned_at.is_(None)
            )
        )
        for assignment in open_assignments.all():
            a_before = snapshot(assignment)
            assignment.unassigned_at = max(now, assignment.assigned_at)
            assignment.unassigned_by = self.actor.id
            self.audit.changed(assignment, a_before)
        await self.session.commit()
        return user

    async def _ensure_not_last_admin(self, user: User) -> None:
        if user.role is not UserRole.ADMIN:
            return
        admins = await self.session.scalar(
            select(func.count()).where(
                User.role == UserRole.ADMIN,
                User.status == RecordStatus.ACTIVE,
                User.deleted_at.is_(None),
            )
        )
        if (admins or 0) <= 1:
            raise ConflictError("Este ultimul admin activ; biroul nu poate rămâne fără admin")

    # --- Propria parolă ---

    async def change_own_password(self, data: PasswordChange, now: datetime) -> TokenPair:
        """Închide toate sesiunile (inclusiv pe alte dispozitive) și întoarce o sesiune nouă,
        ca utilizatorul să nu fie scos din aplicație."""
        user = self.actor
        if not security.verify_password(user.password_hash, data.current_password):
            raise ValidationFailedError("Parola actuală nu e corectă")
        if data.new_password == data.current_password:
            raise ValidationFailedError("Parola nouă trebuie să difere de cea actuală")
        await self._set_password(user, data.new_password, now, must_change=False)
        return await AuthService(self.session).issue_after_password_change(user, now)

    async def _set_password(
        self, user: User, password: str, now: datetime, must_change: bool
    ) -> None:
        before = snapshot(user)
        user.password_hash = security.hash_password(password)
        user.must_change_password = must_change
        user.session_version += 1
        await self.session.flush()
        self.audit.changed(user, before)
        await self.tokens.revoke_all_for_user(user.id, now)
