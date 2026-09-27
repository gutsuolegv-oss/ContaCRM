"""Botul Telegram: clientul transmite kilometrajul (odometrul de pe bord) al automobilelor.

    python -m app.telegram.bot     (tokenul se pune în aplicație: Setări → Telegram)

Fluxul:
1. Clientul deschide linkul personal din cartelă (t.me/<bot>?start=<cod>): chat-ul se leagă
   de client și apare butonul „🚗 Transmite parcurs”.
2. La apăsare: un singur automobil → botul cere direct odometrul; mai multe → butoane cu
   automobilele, clientul alege.
3. Clientul scrie numărul; se salvează cu regulile din Parc auto (nu mai mic decât luna
   trecută etc.), iar botul confirmă sau spune ce nu e în regulă.
4. O fotografie: deocamdată botul cere cifrele (recunoașterea automată vine mai târziu).

Mesajele Telegram vin prin long polling (getUpdates): nu e nevoie de porturi deschise.
Doar chat-urile private sunt luate în seamă.
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_now, local_today, utc_now
from app.db.base import RecordStatus
from app.db.session import get_sessionmaker
from app.models import (
    BotStatus,
    Client,
    FleetReminder,
    ReminderKind,
    ReminderStatus,
    TelegramChat,
)
from app.services.errors import ConflictError, ServiceError
from app.services.fleet import last_day
from app.services.fleet_reminders import AUTO_GAP, SendWindow, linked_chats, schedule_auto
from app.services.telegram import (
    PREVIOUS_MONTH_UNTIL_DAY,
    SavedReading,
    TelegramBotService,
    VehicleTarget,
    month_label,
    parse_odometer,
    reading_month,
)
from app.services.telegram_bot_settings import bot_row, load_token, report
from app.telegram.api import BotApi, HttpBotApi, TelegramError

log = logging.getLogger("contacrm.telegram")

SEND_BUTTON = "🚗 Transmite parcurs"
COMMANDS = [{"command": "parcurs", "description": "Transmite kilometrajul automobilului"}]

MAIN_KEYBOARD = {
    "keyboard": [[{"text": SEND_BUTTON}]],
    "resize_keyboard": True,
    "is_persistent": True,
}

NOT_LINKED = (
    "Bună ziua! Botul acesta e folosit de clienții biroului de contabilitate.\n\n"
    "Pentru a începe, deschideți linkul personal primit de la contabilul dumneavoastră."
)
BAD_CODE = "Linkul nu mai este valabil. Cereți contabilului un link nou și deschideți-l din nou."
NOT_A_NUMBER = (
    "Nu am înțeles valoarea. Scrieți doar cifrele kilometrajului de pe bord, de exemplu: 123906"
)
PHOTO = (
    "Am primit fotografia, mulțumim! Recunoașterea automată a kilometrajului din poză va fi "
    "disponibilă în curând. Deocamdată, vă rog să scrieți cifrele de pe bord, de exemplu: 123906"
)
LOCKED = (
    "Datele pentru această lună au fost deja închise de contabil, așa că nu le pot modifica. "
    "Dacă valoarea trimisă anterior e greșită, contactați contabilul."
)


def km(value: int) -> str:
    """123906 → „123 906 km”."""
    return f"{value:,} km".replace(",", " ")


def vehicle_label(target: VehicleTarget) -> str:
    return f"{target.vehicle.plate} · {target.vehicle.model}"


def vehicle_buttons(targets: list[VehicleTarget]) -> dict[str, Any]:
    """Un buton pe rând pentru fiecare automobil; „✓” = luna are deja o valoare, „✓ înscris”
    = foaia de parcurs e emisă (valoarea nu se mai schimbă)."""
    return {
        "inline_keyboard": [
            [
                {
                    "text": vehicle_label(t)
                    + (" ✓ înscris" if t.locked else " ✓" if t.has_reading else ""),
                    "callback_data": f"veh:{t.vehicle.id}",
                }
            ]
            for t in targets
        ]
    }


class Bot:
    """Tratează un update Telegram, într-o sesiune de bază de date."""

    def __init__(
        self,
        api: BotApi,
        session: AsyncSession,
        today: Callable[[], date] = local_today,
    ) -> None:
        self.api = api
        self.service = TelegramBotService(session)
        self.today = today

    async def send(self, chat_id: int, text: str, markup: dict[str, Any] | None = None) -> None:
        await self.api.call("sendMessage", chat_id=chat_id, text=text, reply_markup=markup)

    async def handle(self, update: dict[str, Any]) -> None:
        if "callback_query" in update:
            await self._callback(update["callback_query"])
        elif "message" in update:
            message = update["message"]
            if message.get("chat", {}).get("type") == "private":
                await self._message(message)

    # --- mesaje ---

    async def _message(self, message: dict[str, Any]) -> None:
        chat_id: int = message["chat"]["id"]
        text: str = (message.get("text") or "").strip()

        if text.startswith("/start"):
            code = text.removeprefix("/start").strip()
            if code:
                await self._link(message, code)
                return

        linked = await self.service.active_chat(chat_id)
        if linked is None:
            await self.send(chat_id, NOT_LINKED, {"remove_keyboard": True})
            return
        chat, client = linked

        if text.startswith("/start"):
            await self._welcome(chat_id, client)
        elif text in (SEND_BUTTON, "/parcurs"):
            await self._choose_vehicle(chat, client)
        elif message.get("photo") or message.get("document"):
            await self.send(chat_id, PHOTO, MAIN_KEYBOARD)
        elif chat.pending_vehicle_id is not None and text:
            await self._reading(chat, client, text)
        else:
            await self.send(
                chat_id,
                f"Pentru a transmite kilometrajul, apăsați butonul „{SEND_BUTTON}” de mai jos.",
                MAIN_KEYBOARD,
            )

    async def _link(self, message: dict[str, Any], code: str) -> None:
        chat_id: int = message["chat"]["id"]
        sender = message.get("from", {})
        name = " ".join(p for p in (sender.get("first_name"), sender.get("last_name")) if p)
        client = await self.service.link(code, chat_id, name or None, sender.get("username"))
        if client is None:
            await self.send(chat_id, BAD_CODE, {"remove_keyboard": True})
            return
        await self._welcome(chat_id, client)

    async def _welcome(self, chat_id: int, client: Client) -> None:
        await self.send(
            chat_id,
            f"Bună ziua! Acest chat este legat de {client.name}.\n\n"
            f"Când doriți să transmiteți kilometrajul automobilelor, apăsați „{SEND_BUTTON}”.\n"
            f"Până pe {PREVIOUS_MONTH_UNTIL_DAY} ale lunii, valoarea se înregistrează pentru "
            "luna trecută.",
            MAIN_KEYBOARD,
        )

    async def _choose_vehicle(self, chat: TelegramChat, client: Client) -> None:
        targets = await self.service.targets(client.id, self.today())
        if not targets:
            await self.service.set_pending(chat, None)
            await self.send(
                chat.chat_id,
                f"Pentru {client.name} nu sunt automobile în evidență. "
                "Dacă aveți automobile, spuneți-i contabilului să le adauge.",
                MAIN_KEYBOARD,
            )
        elif len(targets) == 1:
            await self._ask(chat, targets[0])
        else:
            await self.service.set_pending(chat, None)
            await self.send(
                chat.chat_id,
                "Pentru care automobil transmiteți kilometrajul?",
                vehicle_buttons(targets),
            )

    async def _ask(self, chat: TelegramChat, target: VehicleTarget) -> None:
        if target.locked:
            await self._already_recorded(chat, target)
            return
        await self.service.set_pending(chat, target)
        lines = [
            f"Scrieți kilometrajul de pe bord pentru {vehicle_label(target)}, "
            f"luna {month_label(target.year, target.month)}.",
            f"Ultima valoare cunoscută: {km(target.start_odometer)}.",
        ]
        if target.has_reading:
            lines.append("Pentru această lună există deja o valoare; cea nouă o va înlocui.")
        await self.send(chat.chat_id, "\n".join(lines), MAIN_KEYBOARD)

    async def _already_recorded(self, chat: TelegramChat, target: VehicleTarget) -> None:
        """Foaia de parcurs pe lună e emisă: nu mai cerem kilometrajul, spunem ce e înscris
        și, dacă mai sunt automobile fără date, le propunem."""
        await self.service.set_pending(chat, None)
        await self.send(
            chat.chat_id,
            f"✅ Kilometrajul pentru {target.vehicle.plate}, luna "
            f"{month_label(target.year, target.month)}, este deja înscris: "
            f"{km(target.value or 0)}. Foaia de parcurs a fost emisă.\n"
            "Dacă valoarea e greșită, contactați contabilul.",
            MAIN_KEYBOARD,
        )
        remaining = [
            t for t in await self.service.targets(chat.client_id, self.today()) if not t.has_reading
        ]
        if remaining:
            await self.send(
                chat.chat_id, "Mai aveți de transmis pentru:", vehicle_buttons(remaining)
            )

    async def _reading(self, chat: TelegramChat, client: Client, text: str) -> None:
        today = self.today()
        target = await self.service.pending_target(chat, today)
        if target is None:
            await self.service.set_pending(chat, None)
            await self._choose_vehicle(chat, client)
            return
        value = parse_odometer(text)
        if value is None:
            await self.send(chat.chat_id, NOT_A_NUMBER, MAIN_KEYBOARD)
            return
        try:
            saved = await self.service.save(chat, target, value, today)
        except ConflictError:
            await self.service.set_pending(chat, None)
            await self.send(chat.chat_id, LOCKED, MAIN_KEYBOARD)
            return
        except ServiceError as e:
            # ex. valoare mai mică decât luna trecută; clientul poate scrie din nou
            await self.send(
                chat.chat_id,
                f"⚠️ Valoarea nu a fost înregistrată: {e.message}.\nVerificați și scrieți din nou.",
                MAIN_KEYBOARD,
            )
            return
        await self._confirm(chat, client, saved, today)

    async def _confirm(
        self, chat: TelegramChat, client: Client, saved: SavedReading, today: date
    ) -> None:
        action = "Am actualizat" if saved.replaced else "Am înregistrat"
        await self.send(
            chat.chat_id,
            f"✅ {action} {km(saved.value)} pentru {saved.vehicle.plate}, "
            f"luna {month_label(saved.year, saved.month)}.\n"
            f"Parcurs în lună: {km(saved.km)}. Mulțumim!",
            MAIN_KEYBOARD,
        )
        remaining = [t for t in await self.service.targets(client.id, today) if not t.has_reading]
        if remaining:
            await self.send(
                chat.chat_id, "Mai aveți de transmis pentru:", vehicle_buttons(remaining)
            )

    # --- butoane ---

    async def _callback(self, query: dict[str, Any]) -> None:
        await self.api.call("answerCallbackQuery", callback_query_id=query["id"])
        chat_id = query.get("message", {}).get("chat", {}).get("id")
        data: str = query.get("data") or ""
        if chat_id is None or not data.startswith("veh:"):
            return
        linked = await self.service.active_chat(chat_id)
        if linked is None:
            await self.send(chat_id, NOT_LINKED, {"remove_keyboard": True})
            return
        chat, client = linked
        # doar automobilele clientului legat (butoanele vechi sau falsificate nu trec)
        target = next(
            (
                t
                for t in await self.service.targets(client.id, self.today())
                if str(t.vehicle.id) == data.removeprefix("veh:")
            ),
            None,
        )
        if target is None:
            await self._choose_vehicle(chat, client)
            return
        await self._ask(chat, target)


# --- reamintiri ---


def reminder_text(kind: ReminderKind, client: Client, year: int, month: int, today: date) -> str:
    label = month_label(year, month)
    if kind is ReminderKind.AUTO_REQUEST:
        # amânată (weekend, în afara orelor): luna poate fi deja încheiată
        ended = today > last_day(year, month)
        intro = f"Bună ziua! Luna {label} {'s-a încheiat' if ended else 'se încheie'}."
    elif kind is ReminderKind.AUTO_REMINDER:
        intro = f"Reamintire: încă nu am primit kilometrajul pentru {label}."
    else:
        intro = f"Bună ziua! Contabilul vă roagă să transmiteți kilometrajul pentru {label}."
    return f"{intro}\n\nPentru {client.name}, apăsați pe automobil și scrieți cifrele de pe bord:"


async def deliver_reminders(api: BotApi, session: AsyncSession, now: datetime) -> int:
    """Trimite reamintirile din coadă (automate și manuale), doar în intervalul de trimitere
    din Setări. Întoarce câte au fost tratate (cele amânate rămân în coadă)."""
    if not SendWindow.of(await bot_row(session)).contains(now):
        await session.commit()
        return 0
    today = now.date()
    queued = (
        await session.scalars(
            select(FleetReminder)
            .where(FleetReminder.status == ReminderStatus.QUEUED)
            .order_by(FleetReminder.id)
            .limit(50)
        )
    ).all()
    service = TelegramBotService(session)
    handled = 0
    for reminder in queued:
        period = (reminder.year, reminder.month)
        if reminder.kind is not ReminderKind.MANUAL:
            recent = await session.scalar(
                select(FleetReminder.id).where(
                    FleetReminder.client_id == reminder.client_id,
                    FleetReminder.year == reminder.year,
                    FleetReminder.month == reminder.month,
                    FleetReminder.status == ReminderStatus.SENT,
                    FleetReminder.sent_at > utc_now() - AUTO_GAP,
                )
            )
            if recent is not None:
                continue  # clientul a primit deja un mesaj azi: mai așteaptă
        handled += 1
        reminder.sent_at = utc_now()
        client = await session.get(Client, reminder.client_id)
        if client is None or client.status != RecordStatus.ACTIVE:
            reminder.status, reminder.note = ReminderStatus.SKIPPED, "Clientul nu mai e activ"
        elif reading_month(today) != period:
            reminder.status = ReminderStatus.SKIPPED
            reminder.note = "Luna s-a schimbat între timp; botul primește date pentru altă lună"
        else:
            targets = [
                t
                for t in await service.targets(client.id, today)
                if (t.year, t.month) == period and not t.has_reading
            ]
            chats = await linked_chats(session, client.id)
            if not targets:
                reminder.status = ReminderStatus.SKIPPED
                reminder.note = "Toate automobilele aveau deja date"
            elif not chats:
                reminder.status = ReminderStatus.SKIPPED
                reminder.note = "Clientul nu are Telegram legat"
            else:
                text = reminder_text(reminder.kind, client, *period, today)
                errors = []
                for chat in chats:
                    try:
                        await api.call(
                            "sendMessage",
                            chat_id=chat.chat_id,
                            text=text,
                            reply_markup=vehicle_buttons(targets),
                        )
                        reminder.chats += 1
                    except TelegramError as e:
                        errors.append(str(e))
                reminder.vehicles = len(targets)
                reminder.status = ReminderStatus.SENT if reminder.chats else ReminderStatus.FAILED
                if errors:
                    reminder.note = f"{len(errors)} chat-uri n-au primit (botul blocat?)"[:255]
                    log.warning("Reamintirea %s: %s", reminder.id, "; ".join(errors))
        await session.commit()
    return handled


# Fără token: cât așteaptă până verifică din nou Setările. Cu token: cât ține deschisă o
# cerere getUpdates (long polling). Între ele, procesul își raportează starea în bază.
IDLE_SECONDS = 10
POLL_SECONDS = 10
RETRY_SECONDS = 30


def explain(error: TelegramError) -> str:
    """Mesajul pentru admin (în Setări) când Telegram nu acceptă botul."""
    if error.status == 401:
        return "Telegram nu acceptă tokenul; verifică-l la @BotFather și salvează-l din nou"
    if error.status == 409:
        return "Botul e folosit deja de alt program (alt proces sau un webhook)"
    return f"Telegram nu răspunde ({error})"


async def run() -> None:
    """Bucla botului. Tokenul vine din Setări (criptat în bază): un token nou sau șters se
    preia fără repornire, la cel mult POLL_SECONDS."""
    sessions = get_sessionmaker()
    api: HttpBotApi | None = None
    active: str | None = None  # tokenul cu care rulează `api`
    offset: int | None = None
    healthy = False

    async def status(value: BotStatus | None = None, **kw: str | None) -> None:
        async with sessions() as session:
            await report(session, value, **kw)

    while True:
        async with sessions() as session:
            token = await load_token(session)

        if token != active:
            if api is not None:
                await api.aclose()
            api, active, offset, healthy = None, None, None, False
            if token is None:
                log.info("Fără token: aștept configurarea din Setări")
            else:
                candidate = HttpBotApi(token)
                try:
                    me = await candidate.call("getMe")
                    await candidate.call("setMyCommands", commands=COMMANDS)
                except TelegramError as e:
                    await candidate.aclose()
                    log.warning("Tokenul nu merge: %s", e)
                    await status(BotStatus.ERROR, message=explain(e))
                    await asyncio.sleep(RETRY_SECONDS)
                    continue
                api, active, healthy = candidate, token, True
                await status(BotStatus.CONNECTED, username=me.get("username"))
                log.info("Botul @%s pornit (long polling)", me.get("username"))

        if api is None:
            await status()
            await asyncio.sleep(IDLE_SECONDS)
            continue

        try:
            updates = await api.call(
                "getUpdates",
                offset=offset,
                timeout=POLL_SECONDS,
                allowed_updates=["message", "callback_query"],
            )
        except TelegramError as e:
            log.warning("getUpdates: %s", e)
            await status(BotStatus.ERROR, message=explain(e))
            healthy = False
            if e.status == 401:
                active = None  # tokenul a fost revocat: se reverifică de la zero
            await asyncio.sleep(5)
            continue
        try:
            async with sessions() as session:
                await schedule_auto(session, local_now())
            async with sessions() as session:
                await deliver_reminders(api, session, local_now())
        except Exception:
            log.exception("Reamintirile nu au putut fi trimise")
        if healthy:
            await status()  # semn de viață
        else:
            healthy = True
            await status(BotStatus.CONNECTED)

        for update in updates:
            offset = update["update_id"] + 1
            try:
                async with sessions() as session:
                    await Bot(api, session).handle(update)
            except Exception:
                # un mesaj care produce o eroare nu oprește botul
                log.exception("Update %s netratat", update.get("update_id"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # httpx jurnalizează URL-ul fiecărei cereri, iar URL-ul Bot API conține tokenul
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    asyncio.run(run())


if __name__ == "__main__":
    main()
