"""/api/settings — setările biroului (datele organizației). Citire: orice utilizator
autentificat; modificare: doar admin (verificat în SettingsService)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models import Organization
from app.schemas.settings import OrganizationOut, OrganizationUpdate
from app.services.settings import SettingsService

router = APIRouter(prefix="/api/settings", tags=["setări"])


@router.get("/organization", response_model=OrganizationOut)
async def get_organization(session: SessionDep, user: CurrentUser) -> Organization:
    return await SettingsService(session, user).organization()


@router.patch("/organization", response_model=OrganizationOut)
async def update_organization(
    body: OrganizationUpdate, session: SessionDep, user: CurrentUser
) -> Organization:
    return await SettingsService(session, user).update_organization(body)
