"""Setări → Telegram: tokenul (criptat, niciodată întors) și starea raportată de bot."""

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.models import AuditLog, BotStatus, TelegramBot, UserRole
from app.services.telegram_bot_settings import bot_username, load_token, report
from tests.integration.conftest import AuthHeaders

URL = "/api/settings/telegram-bot"
TOKEN = "123456789:AAHfakeTokenForTests_abcdefghijklmnopq"  # noqa: S105  # token fals


async def test_admin_sets_token_others_cannot(
    api: AsyncClient, auth: AuthHeaders, session: AsyncSession
) -> None:
    _, admin = await auth(UserRole.ADMIN)
    _, director = await auth(UserRole.DIRECTOR)
    _, contabil = await auth(UserRole.CONTABIL)

    empty = (await api.get(URL, headers=director)).json()
    assert (empty["configured"], empty["status"], empty["running"]) == (
        False,
        "not_configured",
        False,
    )
    assert (await api.get(URL, headers=contabil)).status_code == 403
    assert (await api.put(URL, json={"token": TOKEN}, headers=director)).status_code == 403
    bad = await api.put(URL, json={"token": "nu-e-un-token"}, headers=admin)
    assert bad.status_code == 422

    resp = await api.put(URL, json={"token": f"  {TOKEN} "}, headers=admin)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["configured"], body["token_hint"], body["status"]) == (True, "…nopq", "pending")
    assert TOKEN not in resp.text

    # în bază: criptat; în jurnal: doar indiciul
    row = await session.scalar(select(TelegramBot))
    assert row is not None and row.token_encrypted and TOKEN not in row.token_encrypted
    assert await load_token(session) == TOKEN
    logs = (
        await session.scalars(select(AuditLog).where(AuditLog.entity_type == "telegram_bot"))
    ).all()
    assert logs and all(TOKEN not in str(log.new_values) for log in logs)
    assert all("token_encrypted" not in (log.new_values or {}) for log in logs)

    # oprirea botului
    off = (await api.put(URL, json={"token": None}, headers=admin)).json()
    assert (off["configured"], off["status"], off["token_hint"]) == (False, "not_configured", None)
    assert await load_token(session) is None


async def test_status_reported_by_the_bot(
    api: AsyncClient, auth: AuthHeaders, session: AsyncSession
) -> None:
    _, admin = await auth(UserRole.ADMIN)
    await api.put(URL, json={"token": TOKEN}, headers=admin)
    assert await bot_username(session) is None  # încă neverificat: fără linkuri

    await report(session, BotStatus.CONNECTED, username="ContaCRM_bot")
    body = (await api.get(URL, headers=admin)).json()
    assert (body["status"], body["username"], body["running"]) == (
        "connected",
        "ContaCRM_bot",
        True,
    )
    assert await bot_username(session) == "ContaCRM_bot"

    await report(session, BotStatus.ERROR, message="Telegram nu acceptă tokenul")
    body = (await api.get(URL, headers=admin)).json()
    assert (body["status"], body["status_message"]) == ("error", "Telegram nu acceptă tokenul")
    assert await bot_username(session) is None

    # fără semn de viață recent: procesul botului nu rulează
    row = await session.scalar(select(TelegramBot))
    assert row is not None
    row.checked_at = utc_now() - timedelta(minutes=5)
    await session.commit()
    assert (await api.get(URL, headers=admin)).json()["running"] is False


async def test_unreadable_token_is_reported(session: AsyncSession) -> None:
    unreadable = "gAAAA-nu-se-poate-citi"
    session.add(TelegramBot(token_encrypted=unreadable, status=BotStatus.CONNECTED))
    await session.flush()
    assert await load_token(session) is None
    row = await session.scalar(select(TelegramBot))
    assert row is not None and row.status is BotStatus.ERROR
    assert row.status_message is not None and "APP_SECRET_KEY" in row.status_message
