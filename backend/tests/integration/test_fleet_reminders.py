"""Reamintirile pe Telegram pentru odometru: automate (programate de bot) și manuale (API)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.secrets import encrypt
from app.models import (
    BotStatus,
    Client,
    FleetReminder,
    FuelType,
    OdometerReading,
    ReadingSource,
    ReminderKind,
    ReminderStatus,
    TelegramBot,
    TelegramChat,
    User,
    UserRole,
    Vehicle,
)
from app.services.fleet_reminders import schedule_auto
from app.services.telegram_bot_settings import TOKEN_PURPOSE
from app.telegram.api import TelegramError
from app.telegram.bot import deliver_reminders
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import assign, make_client

CHAT = 777001


class FakeApi:
    def __init__(self, blocked: set[int] | None = None) -> None:
        self.sent: list[dict[str, Any]] = []
        self.blocked = blocked or set()

    async def call(self, method: str, **params: Any) -> Any:
        if params.get("chat_id") in self.blocked:
            raise TelegramError("sendMessage: 403 Forbidden: bot was blocked by the user", 403)
        self.sent.append(params)
        return True


class World:
    agro: Client  # automobil fără date, chat legat
    other: Client  # automobil fără date, fără chat
    done: Client  # chat legat, dar automobilul are date
    hilux: Vehicle
    bot: TelegramBot
    ana: dict[str, str]
    ion: dict[str, str]
    ana_user: User


def vehicle(client: Client, plate: str) -> Vehicle:
    return Vehicle(
        client_id=client.id,
        plate=plate,
        model="Dacia Logan",
        fuel_type=FuelType.BENZINA,
        fuel_norm=Decimal("7.2"),
        initial_odometer=10000,
    )


@pytest.fixture
async def w(session: AsyncSession, auth: AuthHeaders) -> World:
    world = World()
    world.bot = TelegramBot(
        token_encrypted=encrypt("1:x", TOKEN_PURPOSE),
        username="ContaCRM_bot",
        status=BotStatus.CONNECTED,
    )
    world.agro = await make_client(session, "1003600012345", name="Agro-Nord SRL")
    world.other = await make_client(session, "1002600054321", name="Vinăria Codru SA")
    world.done = await make_client(session, "1010600023456", name="Print Studio SRL")
    world.hilux = vehicle(world.agro, "BLA 482")
    done_car = vehicle(world.done, "CDK 540")
    session.add_all([world.bot, world.hilux, vehicle(world.other, "CAU 301"), done_car])
    await session.flush()
    session.add_all(
        [
            TelegramChat(client_id=world.agro.id, chat_id=CHAT),
            TelegramChat(client_id=world.done.id, chat_id=CHAT + 1),
            OdometerReading(
                vehicle_id=done_car.id,
                year=2026,
                month=9,
                end_odometer=11000,
                source=ReadingSource.EMAIL,
                received_on=date(2026, 9, 27),
            ),
        ]
    )
    world.ana_user, world.ana = await auth(UserRole.CONTABIL)
    _, world.ion = await auth(UserRole.CONTABIL)
    await assign(session, world.agro, world.ana_user)
    await assign(session, world.other, world.ana_user)
    await session.flush()
    return world


async def reminders(session: AsyncSession) -> list[FleetReminder]:
    return list((await session.scalars(select(FleetReminder).order_by(FleetReminder.id))).all())


async def test_auto_request_once_and_delivered(session: AsyncSession, w: World) -> None:
    assert await schedule_auto(session, datetime(2026, 9, 30, 14, 0)) == 0
    # 15:00 în ultima zi: doar Agro (are chat și date lipsă)
    assert await schedule_auto(session, datetime(2026, 9, 30, 15, 5)) == 1
    assert await schedule_auto(session, datetime(2026, 9, 30, 21, 0)) == 0  # nu se dublează
    (req,) = await reminders(session)
    assert (req.client_id, req.kind, req.year, req.month) == (
        w.agro.id,
        ReminderKind.AUTO_REQUEST,
        2026,
        9,
    )

    api = FakeApi()
    await deliver_reminders(api, session, datetime(2026, 9, 30, 15, 10))  # miercuri
    (msg,) = api.sent
    assert msg["chat_id"] == CHAT
    assert "Luna septembrie 2026 se încheie" in msg["text"] and "Agro-Nord SRL" in msg["text"]
    assert msg["reply_markup"]["inline_keyboard"] == [
        [{"text": "BLA 482 · Dacia Logan", "callback_data": f"veh:{w.hilux.id}"}]
    ]
    await session.refresh(req)
    assert (req.status, req.chats, req.vehicles) == (ReminderStatus.SENT, 1, 1)


async def test_auto_reminder_skipped_when_data_arrived(session: AsyncSession, w: World) -> None:
    # pe 3 octombrie, 10:00: reamintire pentru septembrie
    assert await schedule_auto(session, datetime(2026, 10, 3, 10, 30)) == 1
    (rem,) = await reminders(session)
    assert rem.kind is ReminderKind.AUTO_REMINDER
    # între timp, clientul a trimis odometrul
    session.add(
        OdometerReading(
            vehicle_id=w.hilux.id,
            year=2026,
            month=9,
            end_odometer=10500,
            source=ReadingSource.TELEGRAM,
            received_on=date(2026, 10, 3),
        )
    )
    await session.flush()
    api = FakeApi()
    await deliver_reminders(api, session, datetime(2026, 10, 5, 9, 30))  # luni
    assert api.sent == []
    await session.refresh(rem)
    assert (rem.status, rem.note) == (ReminderStatus.SKIPPED, "Toate automobilele aveau deja date")


async def test_auto_reminders_can_be_turned_off(session: AsyncSession, w: World) -> None:
    w.bot.auto_reminders = False
    await session.flush()
    assert await schedule_auto(session, datetime(2026, 9, 30, 15, 5)) == 0


async def test_manual_reminder(api: AsyncClient, session: AsyncSession, w: World) -> None:
    # „azi” în API e 27.09: botul primește date pentru septembrie
    url = f"/api/clients/{w.agro.id}/fleet"
    ok = (
        await api.get(f"{url}/reminders", params={"year": 2026, "month": 9}, headers=w.ana)
    ).json()
    assert (ok["can_remind"], ok["remind_month"], ok["reminders"]) == (True, 9, [])
    august = await api.get(f"{url}/reminders", params={"year": 2026, "month": 8}, headers=w.ana)
    assert "septembrie 2026" in august.json()["blocker"]

    other = await api.get(
        f"/api/clients/{w.other.id}/fleet/reminders",
        params={"year": 2026, "month": 9},
        headers=w.ana,
    )
    assert "nu are Telegram legat" in other.json()["blocker"]
    denied = await api.post(f"/api/clients/{w.other.id}/fleet/remind", headers=w.ana)
    assert denied.status_code == 422
    assert (await api.post(f"{url}/remind", headers=w.ion)).status_code == 404

    sent = await api.post(f"{url}/remind", headers=w.ana)
    assert sent.status_code == 200, sent.text
    (row,) = sent.json()["reminders"]
    assert (row["kind"], row["status"], row["created_by_name"]) == (
        "manual",
        "queued",
        w.ana_user.full_name,
    )
    assert (await api.post(f"{url}/remind", headers=w.ana)).status_code == 409  # dublu-clic

    # procesul botului o trimite; un chat care a blocat botul → eșuată
    blocked = FakeApi(blocked={CHAT})
    await deliver_reminders(blocked, session, datetime(2026, 9, 28, 10, 0))  # luni
    after = (
        await api.get(f"{url}/reminders", params={"year": 2026, "month": 9}, headers=w.ana)
    ).json()
    assert after["reminders"][0]["status"] == "failed"
    assert "n-au primit" in after["reminders"][0]["note"]


async def test_sending_window_and_gap(session: AsyncSession, w: World) -> None:
    # 31 octombrie 2026 e sâmbătă: cererile de la 15:00 intră în coadă, dar nu pleacă
    # (pe octombrie, și Print Studio are automobilul fără date)
    assert await schedule_auto(session, datetime(2026, 10, 31, 15, 5)) == 2
    api = FakeApi()
    assert await deliver_reminders(api, session, datetime(2026, 10, 31, 15, 6)) == 0
    assert await deliver_reminders(api, session, datetime(2026, 11, 2, 8, 59)) == 0  # luni, devreme
    assert {r.status for r in await reminders(session)} == {ReminderStatus.QUEUED}

    # luni la 9: pleacă, cu textul potrivit (luna s-a încheiat)
    assert await deliver_reminders(api, session, datetime(2026, 11, 2, 9, 0)) == 2
    assert [m["chat_id"] for m in api.sent] == [CHAT, CHAT + 1]
    assert "Luna octombrie 2026 s-a încheiat" in api.sent[0]["text"]

    # reamintirile de pe 3 intră în coadă, dar așteaptă 24 de ore de la cerere
    assert await schedule_auto(session, datetime(2026, 11, 3, 10, 30)) == 2
    assert await deliver_reminders(api, session, datetime(2026, 11, 3, 10, 31)) == 0
    assert len(api.sent) == 2


async def test_reminder_settings_api(api: AsyncClient, auth: AuthHeaders, w: World) -> None:
    _, admin = await auth(UserRole.ADMIN)
    _, director = await auth(UserRole.DIRECTOR)
    url = "/api/settings/telegram-bot/reminders"
    body = {"auto_reminders": True, "weekdays": [5, 1, 3, 3], "start": "08:30", "end": "17:00"}
    assert (await api.put(url, json=body, headers=director)).status_code == 403
    bad_values: list[dict[str, Any]] = [
        {"start": "18:00", "end": "09:00"},
        {"weekdays": []},
        {"weekdays": [8]},
    ]
    for bad in bad_values:
        assert (await api.put(url, json={**body, **bad}, headers=admin)).status_code == 422
    saved = (await api.put(url, json=body, headers=admin)).json()
    assert (saved["reminder_weekdays"], saved["reminder_from"], saved["reminder_to"]) == (
        [1, 3, 5],
        "08:30:00",
        "17:00:00",
    )
    overview = await api.get(
        f"/api/clients/{w.agro.id}/fleet/reminders",
        params={"year": 2026, "month": 9},
        headers=w.ana,
    )
    assert overview.json()["send_window"] == "L, Mi, V, 08:30-17:00"
