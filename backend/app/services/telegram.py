"""Telegram: legarea chat-urilor de clienți (din cartelă) și ce face botul cu ele.

Cartela (utilizator logat, aceleași drepturi ca la cartelă): linkul de legare al clientului,
regenerarea lui, chat-urile legate și închiderea unei legături.

Botul (fără utilizator logat): leagă un chat printr-un cod, găsește clientul unui chat,
automobilele lui, luna pentru care se trimite odometrul și salvează citirea cu aceleași
reguli ca în tabul Parc auto (FleetService.record_reading).
"""

import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.clock import utc_now
from app.db.base import RecordStatus
from app.models import (
    Client,
    OdometerReading,
    ReadingSource,
    TelegramChat,
    TelegramLinkCode,
    User,
    Vehicle,
)
from app.repositories.fleet import VehicleRepository
from app.schemas.fleet import ReadingIn
from app.schemas.telegram import TelegramChatOut, TelegramStatusOut
from app.services.access import get_visible_client
from app.services.audit import AuditService, snapshot
from app.services.errors import NotFoundError, conflict_guard
from app.services.fleet import FleetService
from app.services.telegram_bot_settings import bot_username

# Până în această zi a lunii inclusiv, odometrul trimis e pentru luna trecută.
PREVIOUS_MONTH_UNTIL_DAY = 10

# grupe de mii despărțite prin spațiu (și cel neîntrerupt), punct, virgulă sau apostrof
_GROUPED = re.compile(r"\d{1,3}(?:[ .,'\u00a0\u202f]\d{3})+")


def parse_odometer(text: str) -> int | None:
    """Numărul de pe bord din textul clientului: „123906”, „123 906”, „123.906 km”.
    `None` dacă nu e un număr întreg de kilometri (ex. „123,5” sau „aproape 100000”)."""
    value = re.sub(r"\s*(km|км)\.?\s*$", "", text.strip(), flags=re.IGNORECASE).strip()
    if re.fullmatch(r"\d{1,7}", value) or _GROUPED.fullmatch(value):
        number = int(re.sub(r"\D", "", value))
        return number if number <= 9_999_999 else None
    return None


MONTHS = [
    "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
    "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
]  # fmt: skip


def month_label(year: int, month: int) -> str:
    """(2026, 9) → „septembrie 2026”."""
    return f"{MONTHS[month - 1]} {year}"


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def reading_month(today: date) -> tuple[int, int]:
    """Luna pentru care se înregistrează odometrul trimis azi: luna trecută până pe 10
    (trimis din nou, înlocuiește valoarea), apoi luna curentă. Un odometru „de sfârșit
    de lună” trimis pe 3 octombrie e al lui septembrie, chiar dacă septembrie are deja date."""
    if today.day <= PREVIOUS_MONTH_UNTIL_DAY:
        return previous_month(today.year, today.month)
    return (today.year, today.month)


def link_url(username: str, code: str) -> str:
    return f"https://t.me/{username}?start={code}"


# --- Cartela clientului ---


class TelegramLinkService:
    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)

    async def status(self, client_id: int) -> TelegramStatusOut:
        client = await get_visible_client(self.session, self.actor, client_id)
        code = await self.session.scalar(
            select(TelegramLinkCode.code).where(TelegramLinkCode.client_id == client.id)
        )
        chats = await self.session.scalars(
            select(TelegramChat)
            .where(TelegramChat.client_id == client.id, TelegramChat.unlinked_at.is_(None))
            .order_by(TelegramChat.created_at)
        )
        username = await bot_username(self.session)
        return TelegramStatusOut(
            bot_configured=username is not None,
            link=link_url(username, code) if code and username else None,
            chats=[TelegramChatOut.model_validate(c) for c in chats],
        )

    async def regenerate_code(self, client_id: int) -> TelegramStatusOut:
        """Cod nou pentru client; cel vechi nu mai leagă chat-uri noi (cele legate rămân)."""
        client = await get_visible_client(self.session, self.actor, client_id)
        row = await self.session.scalar(
            select(TelegramLinkCode).where(TelegramLinkCode.client_id == client.id)
        )
        async with conflict_guard(self.session, "Codul nu a putut fi generat (reîncearcă)"):
            if row is None:
                row = TelegramLinkCode(
                    client_id=client.id, code=secrets.token_urlsafe(12), created_by=self.actor.id
                )
                self.session.add(row)
                await self.session.flush()
                self.audit.created(row)
            else:
                before = snapshot(row)
                row.code = secrets.token_urlsafe(12)
                row.created_by = self.actor.id
                await self.session.flush()
                self.audit.changed(row, before)
        await self.session.commit()
        return await self.status(client.id)

    async def unlink(self, chat_row_id: int, now: datetime) -> TelegramStatusOut:
        chat = await self.session.get(TelegramChat, chat_row_id)
        if chat is None or chat.unlinked_at is not None:
            raise NotFoundError("Legătura nu există")
        try:
            await get_visible_client(self.session, self.actor, chat.client_id)
        except NotFoundError as e:
            raise NotFoundError("Legătura nu există") from e
        before = snapshot(chat)
        chat.unlinked_at = now
        chat.unlinked_by = self.actor.id
        chat.pending_vehicle_id = chat.pending_year = chat.pending_month = None
        self.audit.changed(chat, before)
        await self.session.commit()
        return await self.status(chat.client_id)


# --- Botul ---


@dataclass
class VehicleTarget:
    """Un automobil al clientului și luna pentru care i se cere odometrul acum."""

    vehicle: Vehicle
    year: int
    month: int
    start_odometer: int
    has_reading: bool  # luna are deja date (trimiterea le va înlocui)
    value: int | None = None  # odometrul deja înscris pe lună
    waybill: str | None = None  # numărul foii emise: luna e închisă, nu se mai modifică

    @property
    def locked(self) -> bool:
        return self.waybill is not None


@dataclass
class SavedReading:
    vehicle: Vehicle
    year: int
    month: int
    value: int
    km: int
    replaced: bool


class TelegramBotService:
    """Tot ce face botul în bază. Nu are utilizator: accesul îl dă legătura chat-client."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit = AuditService(session, None)
        self.vehicles = VehicleRepository(session)

    async def active_chat(self, chat_id: int) -> tuple[TelegramChat, Client] | None:
        """Legătura activă a chat-ului, dacă clientul e încă activ (nearhivat)."""
        row = (
            await self.session.execute(
                select(TelegramChat, Client)
                .join(Client, Client.id == TelegramChat.client_id)
                .where(
                    TelegramChat.chat_id == chat_id,
                    TelegramChat.unlinked_at.is_(None),
                    Client.status == RecordStatus.ACTIVE,
                    Client.deleted_at.is_(None),
                )
            )
        ).one_or_none()
        return None if row is None else (row[0], row[1])

    async def link(
        self, code: str, chat_id: int, name: str | None, username: str | None
    ) -> Client | None:
        """Leagă chat-ul de clientul codului. `None` dacă codul nu e valabil. Dacă chat-ul era
        legat de alt client, legătura veche se închide."""
        client = await self.session.scalar(
            select(Client)
            .join(TelegramLinkCode, TelegramLinkCode.client_id == Client.id)
            .where(
                TelegramLinkCode.code == code,
                Client.status == RecordStatus.ACTIVE,
                Client.deleted_at.is_(None),
            )
        )
        if client is None:
            return None
        current = await self.session.scalar(
            select(TelegramChat).where(
                TelegramChat.chat_id == chat_id, TelegramChat.unlinked_at.is_(None)
            )
        )
        if current is not None and current.client_id == client.id:
            current.tg_name, current.tg_username = name, username
            await self.session.commit()
            return client
        if current is not None:
            before = snapshot(current)
            current.unlinked_at = utc_now()
            current.pending_vehicle_id = current.pending_year = current.pending_month = None
            await self.session.flush()
            self.audit.changed(current, before)
        chat = TelegramChat(
            client_id=client.id, chat_id=chat_id, tg_name=name, tg_username=username
        )
        self.session.add(chat)
        await self.session.flush()
        self.audit.created(chat)
        await self.session.commit()
        return client

    async def targets(self, client_id: int, today: date) -> list[VehicleTarget]:
        """Automobilele active ale clientului, fiecare cu luna în care intră odometrul
        trimis azi."""
        vehicles = await self.vehicles.list_for_client(client_id)
        readings = (
            await self.session.scalars(
                select(OdometerReading)
                .where(OdometerReading.vehicle_id.in_([v.id for v in vehicles]))
                .options(selectinload(OdometerReading.waybill))
            )
        ).all()
        year, month = reading_month(today)
        result = []
        for v in vehicles:
            mine = {(r.year, r.month): r for r in readings if r.vehicle_id == v.id}
            earlier = [r for k, r in mine.items() if k < (year, month)]
            start = (
                max(earlier, key=lambda r: (r.year, r.month)).end_odometer
                if earlier
                else (v.initial_odometer)
            )
            current = mine.get((year, month))
            result.append(
                VehicleTarget(
                    v,
                    year,
                    month,
                    start,
                    current is not None,
                    current.end_odometer if current else None,
                    current.waybill.number if current and current.waybill else None,
                )
            )
        return result

    async def set_pending(self, chat: TelegramChat, target: VehicleTarget | None) -> None:
        chat.pending_vehicle_id = target.vehicle.id if target else None
        chat.pending_year = target.year if target else None
        chat.pending_month = target.month if target else None
        await self.session.commit()

    async def pending_target(self, chat: TelegramChat, today: date) -> VehicleTarget | None:
        """Automobilul pentru care se așteaptă odometrul, recalculat pentru azi (dacă între timp
        a fost scos din evidență, nu mai e nimic de așteptat)."""
        if chat.pending_vehicle_id is None:
            return None
        return next(
            (
                t
                for t in await self.targets(chat.client_id, today)
                if t.vehicle.id == chat.pending_vehicle_id
            ),
            None,
        )

    async def save(
        self, chat: TelegramChat, target: VehicleTarget, value: int, today: date
    ) -> SavedReading:
        """Salvează odometrul cu regulile din Parc auto. Erorile de validare (ServiceError) le
        prinde botul și i le arată clientului."""
        await FleetService(self.session, None).record_reading(
            target.vehicle,
            target.year,
            target.month,
            ReadingIn(end_odometer=value, source=ReadingSource.TELEGRAM, received_on=today),
            today,
        )
        await self.set_pending(chat, None)
        return SavedReading(
            target.vehicle,
            target.year,
            target.month,
            value,
            value - target.start_odometer,
            target.has_reading,
        )
