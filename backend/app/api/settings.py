"""/api/settings — setările biroului: datele organizației (citire: orice utilizator; modificare:
doar admin) și botul Telegram (starea: admin și director; tokenul: doar admin)."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models import Organization
from app.schemas.settings import OrganizationOut, OrganizationUpdate
from app.schemas.telegram import BotSettingsOut, BotTokenIn
from app.services.settings import SettingsService
from app.services.telegram_bot_settings import BotSettingsService

router = APIRouter(prefix="/api/settings", tags=["setări"])


@router.get("/organization", response_model=OrganizationOut)
async def get_organization(session: SessionDep, user: CurrentUser) -> Organization:
    return await SettingsService(session, user).organization()


@router.patch("/organization", response_model=OrganizationOut)
async def update_organization(
    body: OrganizationUpdate, session: SessionDep, user: CurrentUser
) -> Organization:
    return await SettingsService(session, user).update_organization(body)


@router.get("/telegram-bot", response_model=BotSettingsOut)
async def get_telegram_bot(session: SessionDep, user: CurrentUser) -> BotSettingsOut:
    """Starea botului (admin și director). Tokenul nu se întoarce niciodată."""
    return await BotSettingsService(session, user).get()


@router.put("/telegram-bot", response_model=BotSettingsOut)
async def set_telegram_bot(
    body: BotTokenIn, session: SessionDep, user: CurrentUser
) -> BotSettingsOut:
    """Doar admin. Token nou: procesul botului îl verifică în câteva secunde; null: botul se
    oprește."""
    return await BotSettingsService(session, user).set_token(body.token)
