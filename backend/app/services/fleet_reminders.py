"""Reamintiri pe Telegram pentru odometrul automobilelor.

Automate (le programează și le trimite procesul botului, o singură dată per client și lună):
- ultima zi a lunii, de la 15:00: cererea („luna se încheie, transmiteți kilometrajul”);
  dacă botul era oprit atunci, cererea pleacă pe 1 sau 2 ale lunii următoare;
- pe 3 ale lunii următoare, de la 10:00 (până pe 10): reamintirea, doar dacă tot lipsesc date.

Manuale: contabilul apasă „Reamintește” în Parc auto sau în grilă. Doar pentru luna în care
botul înregistrează acum odometrul (altfel clientul ar răspunde pentru altă lună).

Toate pleacă doar în intervalul de trimitere din Setări (implicit luni-vineri, 09:00-18:00);
în afara lui așteaptă în coadă. Între două mesaje automate către același client trec cel puțin
24 de ore (ex. cererea amânată din weekend și reamintirea de luni nu pleacă în aceeași zi).

Aici se creează reamintirile (coada); trimiterea o face procesul botului (app.telegram.bot).
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import utc_now
from app.db.base import RecordStatus
from app.models import (
    Client,
    FleetReminder,
    OdometerReading,
    ReminderKind,
    ReminderStatus,
    TelegramBot,
    TelegramChat,
    User,
    Vehicle,
)
from app.schemas.fleet import ReminderOut, RemindersOut
from app.services.access import get_visible_client
from app.services.audit import AuditService
from app.services.errors import ConflictError, ValidationFailedError
from app.services.fleet import last_day
from app.services.telegram import (
    PREVIOUS_MONTH_UNTIL_DAY,
    month_label,
    previous_month,
    reading_month,
)
from app.services.telegram_bot_settings import bot_row, bot_username

REQUEST_HOUR = 15  # ultima zi a lunii
REMINDER_DAY, REMINDER_HOUR = 3, 10  # luna următoare
# Două reamintiri manuale la același client, prea aproape una de alta: probabil un dublu-clic.
MANUAL_COOLDOWN = timedelta(minutes=10)
# Distanța minimă între două mesaje automate către același client, pentru aceeași lună.
AUTO_GAP = timedelta(hours=24)
WEEKDAYS = ["L", "Ma", "Mi", "J", "V", "S", "D"]


@dataclass(frozen=True)
class SendWindow:
    """Zilele (1 = luni … 7 = duminică) și orele în care pleacă reamintirile."""

    weekdays: frozenset[int]
    start: time
    end: time

    @classmethod
    def of(cls, bot: TelegramBot) -> "SendWindow":
        return cls(frozenset(bot.reminder_weekdays), bot.reminder_from, bot.reminder_to)

    def contains(self, now: datetime) -> bool:
        return now.isoweekday() in self.weekdays and self.start <= now.time() < self.end

    def next_start(self, now: datetime) -> datetime:
        """Acum, dacă intervalul e deschis; altfel începutul următorului interval."""
        if self.contains(now):
            return now
        for days in range(8):
            day = now.date() + timedelta(days=days)
            start = datetime.combine(day, self.start, tzinfo=now.tzinfo)
            if day.isoweekday() in self.weekdays and start > now:
                return start
        return now  # nu se ajunge aici: zilele nu pot fi goale

    def label(self) -> str:
        """„L-V, 09:00-18:00” sau „L, Mi, V, 09:00-18:00”."""
        days = sorted(self.weekdays)
        if days == list(range(days[0], days[-1] + 1)) and len(days) > 2:
            names = f"{WEEKDAYS[days[0] - 1]}-{WEEKDAYS[days[-1] - 1]}"
        else:
            names = ", ".join(WEEKDAYS[d - 1] for d in days)
        return f"{names}, {self.start:%H:%M}-{self.end:%H:%M}"


def due_auto(now: datetime) -> list[tuple[ReminderKind, int, int]]:
    """Reamintirile automate care ar trebui să fi plecat până la `now` (ora locală)."""
    today = now.date()
    due = []
    if today == last_day(today.year, today.month) and now.hour >= REQUEST_HOUR:
        due.append((ReminderKind.AUTO_REQUEST, today.year, today.month))
    year, month = previous_month(today.year, today.month)
    if today.day < REMINDER_DAY or (today.day == REMINDER_DAY and now.hour < REMINDER_HOUR):
        due.append((ReminderKind.AUTO_REQUEST, year, month))  # recuperare, botul era oprit
    elif today.day <= PREVIOUS_MONTH_UNTIL_DAY:
        due.append((ReminderKind.AUTO_REMINDER, year, month))
    return due


async def missing_vehicles(
    session: AsyncSession, year: int, month: int, client_ids: Sequence[int] | None = None
) -> dict[int, list[Vehicle]]:
    """Automobilele active fără odometru pe lună, grupate pe client."""
    stmt = (
        select(Vehicle)
        .outerjoin(
            OdometerReading,
            and_(
                OdometerReading.vehicle_id == Vehicle.id,
                OdometerReading.year == year,
                OdometerReading.month == month,
            ),
        )
        .where(
            OdometerReading.id.is_(None),
            Vehicle.status == RecordStatus.ACTIVE,
            Vehicle.deleted_at.is_(None),
        )
        .order_by(Vehicle.client_id, Vehicle.plate)
    )
    if client_ids is not None:
        stmt = stmt.where(Vehicle.client_id.in_(client_ids))
    result: dict[int, list[Vehicle]] = defaultdict(list)
    for v in await session.scalars(stmt):
        result[v.client_id].append(v)
    return result


async def linked_chats(session: AsyncSession, client_id: int) -> Sequence[TelegramChat]:
    stmt = select(TelegramChat).where(
        TelegramChat.client_id == client_id, TelegramChat.unlinked_at.is_(None)
    )
    return (await session.scalars(stmt)).all()


async def clients_with_chats(
    session: AsyncSession, client_ids: Sequence[int] | None = None
) -> set[int]:
    """Clienții activi care au cel puțin un chat Telegram legat."""
    stmt = (
        select(TelegramChat.client_id)
        .join(Client, Client.id == TelegramChat.client_id)
        .where(
            TelegramChat.unlinked_at.is_(None),
            Client.status == RecordStatus.ACTIVE,
            Client.deleted_at.is_(None),
        )
    )
    if client_ids is not None:
        stmt = stmt.where(TelegramChat.client_id.in_(client_ids))
    return set(await session.scalars(stmt))


async def schedule_auto(session: AsyncSession, now: datetime) -> int:
    """Pune în coadă reamintirile automate scadente (idempotent: indexul unic nu lasă
    dubluri). Întoarce câte s-au adăugat acum."""
    bot = await bot_row(session)
    if not bot.auto_reminders or bot.token_encrypted is None:
        await session.commit()
        return 0
    added = 0
    with_chats = await clients_with_chats(session)
    for kind, year, month in due_auto(now):
        missing = await missing_vehicles(session, year, month, list(with_chats))
        rows = [
            {"client_id": c, "year": year, "month": month, "kind": kind}
            for c in sorted(with_chats & set(missing))
        ]
        if rows:
            result = await session.execute(
                insert(FleetReminder)
                .values(rows)
                .on_conflict_do_nothing(
                    index_elements=["client_id", "year", "month", "kind"],
                    index_where=FleetReminder.kind != ReminderKind.MANUAL,
                )
                .returning(FleetReminder.id)
            )
            added += len(result.all())
    await session.commit()
    return added


async def remind_blockers(
    session: AsyncSession, client_ids: Sequence[int], year: int, month: int, today: date
) -> dict[int, str | None]:
    """Pentru fiecare client: de ce NU se poate trimite acum o reamintire manuală pe luna
    dată (`None` = se poate)."""
    target = reading_month(today)
    connected = await bot_username(session) is not None
    chats = await clients_with_chats(session, client_ids)
    missing = await missing_vehicles(session, year, month, client_ids)
    result: dict[int, str | None] = {}
    for c in client_ids:
        if (year, month) != target:
            result[c] = (
                f"Botul primește acum datele pentru {month_label(*target)}; reamintirea se "
                "trimite doar pentru acea lună"
            )
        elif not connected:
            result[c] = "Botul Telegram nu e conectat (Setări → Telegram)"
        elif c not in chats:
            result[c] = "Clientul nu are Telegram legat: trimite-i linkul din cardul Telegram"
        elif not missing.get(c):
            result[c] = "Toate automobilele au date pe luna aceasta"
        else:
            result[c] = None
    return result


class ReminderService:
    """Reamintirile din cartelă și din grilă (aceleași drepturi ca la cartela clientului)."""

    def __init__(self, session: AsyncSession, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)

    async def overview(
        self, client_id: int, year: int, month: int, today: date, now: datetime
    ) -> RemindersOut:
        client = await get_visible_client(self.session, self.actor, client_id)
        blocker = (await remind_blockers(self.session, [client.id], year, month, today))[client.id]
        rows = (
            await self.session.execute(
                select(FleetReminder, User.full_name)
                .outerjoin(User, User.id == FleetReminder.created_by)
                .where(
                    FleetReminder.client_id == client.id,
                    FleetReminder.year == year,
                    FleetReminder.month == month,
                )
                .order_by(FleetReminder.created_at.desc(), FleetReminder.id.desc())
            )
        ).all()
        target = reading_month(today)
        window = SendWindow.of(await bot_row(self.session))
        await self.session.commit()
        return RemindersOut(
            remind_year=target[0],
            remind_month=target[1],
            can_remind=blocker is None,
            blocker=blocker,
            send_window=window.label(),
            window_open=window.contains(now),
            next_send_at=window.next_start(now),
            reminders=[
                ReminderOut.model_validate(r).model_copy(update={"created_by_name": name})
                for r, name in rows
            ],
        )

    async def remind(self, client_id: int, today: date, now: datetime) -> RemindersOut:
        """Reamintire manuală pentru luna în care botul primește acum datele."""
        client = await get_visible_client(self.session, self.actor, client_id)
        year, month = reading_month(today)
        blocker = (await remind_blockers(self.session, [client.id], year, month, today))[client.id]
        if blocker is not None:
            raise ValidationFailedError(blocker)
        recent = await self.session.scalar(
            select(FleetReminder.id).where(
                FleetReminder.client_id == client.id,
                FleetReminder.kind == ReminderKind.MANUAL,
                FleetReminder.created_at > utc_now() - MANUAL_COOLDOWN,
            )
        )
        if recent is not None:
            raise ConflictError("S-a trimis deja o reamintire în ultimele 10 minute")
        reminder = FleetReminder(
            client_id=client.id,
            year=year,
            month=month,
            kind=ReminderKind.MANUAL,
            status=ReminderStatus.QUEUED,
            created_by=self.actor.id,
        )
        self.session.add(reminder)
        await self.session.flush()
        self.audit.created(reminder)
        await self.session.commit()
        return await self.overview(client.id, year, month, today, now)
