"""Configurarea botului Telegram din Setări (tokenul) și starea raportată de procesul botului.

Tokenul se păstrează criptat și nu se întoarce niciodată prin API. Îl setează doar adminul;
adminul și directorul văd starea (conectat ca @nume, eroare, procesul nu rulează).
"""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.core.secrets import decrypt, encrypt
from app.models import BotStatus, TelegramBot, User, UserRole
from app.schemas.telegram import BotSettingsOut
from app.services.audit import AuditService, snapshot
from app.services.errors import ForbiddenError

TOKEN_PURPOSE = "telegram-bot-token"  # noqa: S105  # eticheta cheii de criptare, nu un secret
# Procesul botului își actualizează `checked_at` cel puțin la fiecare ~30 s.
RUNNING_WINDOW = timedelta(seconds=90)


async def bot_row(session: AsyncSession) -> TelegramBot:
    """Rândul cu configurația botului (se creează la nevoie)."""
    row = await session.scalar(select(TelegramBot).order_by(TelegramBot.id).limit(1))
    if row is None:
        row = TelegramBot()
        session.add(row)
        await session.flush()
    return row


def settings_out(row: TelegramBot, now: datetime) -> BotSettingsOut:
    return BotSettingsOut(
        configured=row.token_encrypted is not None,
        token_hint=row.token_hint,
        username=row.username,
        status=row.status,
        status_message=row.status_message,
        checked_at=row.checked_at,
        running=row.checked_at is not None and now - row.checked_at < RUNNING_WINDOW,
    )


async def bot_username(session: AsyncSession) -> str | None:
    """Numele botului, doar dacă e conectat (altfel linkurile nu ar funcționa)."""
    row = await session.scalar(select(TelegramBot).order_by(TelegramBot.id).limit(1))
    if row is None or row.status is not BotStatus.CONNECTED:
        return None
    return row.username


class BotSettingsService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)

    def _require(self, *roles: UserRole) -> None:
        if self.actor.role not in roles:
            raise ForbiddenError("Acces interzis")

    async def get(self) -> BotSettingsOut:
        self._require(UserRole.ADMIN, UserRole.DIRECTOR)
        row = await bot_row(self.session)
        await self.session.commit()
        return settings_out(row, utc_now())

    async def set_token(self, token: str | None) -> BotSettingsOut:
        """Token nou (procesul botului îl verifică în câteva secunde) sau oprirea botului."""
        self._require(UserRole.ADMIN)
        row = await bot_row(self.session)
        before = snapshot(row)
        row.token_encrypted = encrypt(token, TOKEN_PURPOSE) if token else None
        row.token_hint = f"…{token[-4:]}" if token else None
        row.username = None
        row.status = BotStatus.PENDING if token else BotStatus.NOT_CONFIGURED
        row.status_message = None
        row.updated_by = self.actor.id
        await self.session.flush()
        self.audit.changed(row, before)
        await self.session.commit()
        return settings_out(row, utc_now())


# --- procesul botului ---


async def load_token(session: AsyncSession) -> str | None:
    """Tokenul în clar, pentru procesul botului. `None` dacă nu e setat sau nu se poate
    descifra (starea devine eroare, cu explicație pentru admin)."""
    row = await bot_row(session)
    if row.token_encrypted is None:
        await session.commit()
        return None
    token = decrypt(row.token_encrypted, TOKEN_PURPOSE)
    if token is None and row.status is not BotStatus.ERROR:
        row.status = BotStatus.ERROR
        row.status_message = (
            "Tokenul nu mai poate fi citit (APP_SECRET_KEY s-a schimbat?); introdu-l din nou"
        )
    await session.commit()
    return token


async def report(
    session: AsyncSession,
    status: BotStatus | None = None,
    *,
    username: str | None = None,
    message: str | None = None,
) -> None:
    """Procesul botului: semn de viață (`checked_at`) și, opțional, starea nouă."""
    row = await bot_row(session)
    row.checked_at = utc_now()
    if status is not None and row.token_encrypted is not None:
        row.status = status
        row.status_message = message
        if username is not None:
            row.username = username
    await session.commit()
