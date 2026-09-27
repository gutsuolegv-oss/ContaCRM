"""Setările biroului: datele organizației. Citire: orice utilizator (apar în aplicație);
modificare: doar admin."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Organization, User, UserRole
from app.schemas.settings import OrganizationUpdate
from app.services.audit import AuditService, snapshot
from app.services.classifier import apply_changes
from app.services.errors import ForbiddenError, NotFoundError, conflict_guard


class SettingsService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)

    async def organization(self) -> Organization:
        org = await self.session.get(Organization, self.actor.organization_id)
        if org is None:
            raise NotFoundError("Organizația nu există")
        return org

    async def update_organization(self, data: OrganizationUpdate) -> Organization:
        if self.actor.role is not UserRole.ADMIN:
            raise ForbiddenError("Doar adminul modifică setările")
        org = await self.organization()
        before = snapshot(org)
        async with conflict_guard(self.session, "Există deja o organizație cu acest IDNO"):
            apply_changes(org, data.model_dump(exclude_unset=True))
        self.audit.changed(org, before)
        await self.session.commit()
        return org
