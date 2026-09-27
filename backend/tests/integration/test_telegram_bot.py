"""Botul Telegram cap-coadă, cu un Telegram fals (fără rețea) și baza de test."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    BotStatus,
    Client,
    OdometerReading,
    ReadingSource,
    TelegramBot,
    TelegramChat,
    User,
    UserRole,
    Vehicle,
)
from app.models.fleet import FuelType
from app.telegram.bot import LOCKED, NOT_A_NUMBER, NOT_LINKED, PHOTO, SEND_BUTTON, Bot
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import assign, make_client

OCT_3 = date(2026, 10, 3)  # până pe 10: odometrul intră la septembrie
CHAT = 555001


class FakeApi:
    """Înregistrează apelurile spre Telegram."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, method: str, **params: Any) -> Any:
        self.calls.append((method, params))
        return True

    @property
    def sent(self) -> list[dict[str, Any]]:
        return [p for m, p in self.calls if m == "sendMessage"]

    @property
    def last(self) -> dict[str, Any]:
        return self.sent[-1]

    def texts(self) -> list[str]:
        return [p["text"] for p in self.sent]


def message(text: str = "", chat_id: int = CHAT, **extra: Any) -> dict[str, Any]:
    return {
        "update_id": 1,
        "message": {
            "chat": {"id": chat_id, "type": "private"},
            "from": {"first_name": "Ion", "last_name": "Rotaru", "username": "ionr"},
            "text": text,
            **extra,
        },
    }


def press(vehicle_id: int, chat_id: int = CHAT) -> dict[str, Any]:
    return {
        "update_id": 2,
        "callback_query": {
            "id": "q1",
            "data": f"veh:{vehicle_id}",
            "message": {"chat": {"id": chat_id, "type": "private"}},
        },
    }


class World:
    session: AsyncSession
    api: FakeApi
    agro: Client
    other: Client
    hilux: Vehicle
    logan: Vehicle
    stranger: Vehicle
    admin: dict[str, str]
    ana: dict[str, str]
    ion: dict[str, str]
    ana_user: User

    async def send(self, update: dict[str, Any], today: date = OCT_3) -> None:
        await Bot(self.api, self.session, today=lambda: today).handle(update)


def vehicle(client: Client, plate: str, start: int) -> Vehicle:
    return Vehicle(
        client_id=client.id,
        plate=plate,
        model="Dacia Logan",
        fuel_type=FuelType.BENZINA,
        fuel_norm=Decimal("7.2"),
        initial_odometer=start,
    )


@pytest.fixture
async def w(session: AsyncSession, auth: AuthHeaders) -> World:
    # botul conectat (numele lui formează linkurile din cartelă)
    session.add(TelegramBot(username="ContaCRM_bot", status=BotStatus.CONNECTED))
    world = World()
    world.session, world.api = session, FakeApi()
    world.agro = await make_client(session, "1003600012345", name="Agro-Nord SRL")
    world.other = await make_client(session, "1002600054321", name="Vinăria Codru SA")
    world.hilux = vehicle(world.agro, "BLA 482", 40000)
    world.logan = vehicle(world.agro, "BLA 915", 10000)
    world.stranger = vehicle(world.other, "CAU 301", 5000)
    session.add_all([world.hilux, world.logan, world.stranger])
    _, world.admin = await auth(UserRole.ADMIN)
    world.ana_user, world.ana = await auth(UserRole.CONTABIL)
    _, world.ion = await auth(UserRole.CONTABIL)
    await assign(session, world.agro, world.ana_user)
    await session.flush()
    return world


async def link_code(api: AsyncClient, w: World, client: Client | None = None) -> str:
    """Linkul generat de Ana pentru clientul ei (Agro-Nord) sau de admin pentru altul."""
    headers = w.ana if client is None else w.admin
    resp = await api.post(f"/api/clients/{(client or w.agro).id}/telegram/link", headers=headers)
    assert resp.status_code == 200, resp.text
    link: str = resp.json()["link"]
    assert link.startswith("https://t.me/ContaCRM_bot?start=")
    return link.rsplit("=", 1)[1]


async def test_unlinked_chat_is_asked_for_the_link(w: World) -> None:
    await w.send(message("/start"))
    await w.send(message(SEND_BUTTON))
    assert w.api.texts() == [NOT_LINKED, NOT_LINKED]
    await w.send(message("/start cod-gresit"))
    assert "nu mai este valabil" in w.api.last["text"]


async def test_link_and_send_readings(api: AsyncClient, w: World) -> None:
    code = await link_code(api, w)
    await w.send(message(f"/start {code}"))
    assert "Agro-Nord SRL" in w.api.last["text"]
    assert w.api.last["reply_markup"]["keyboard"] == [[{"text": SEND_BUTTON}]]

    # două automobile: butoane
    await w.send(message(SEND_BUTTON))
    buttons = w.api.last["reply_markup"]["inline_keyboard"]
    assert [row[0]["callback_data"] for row in buttons] == [
        f"veh:{w.hilux.id}",
        f"veh:{w.logan.id}",
    ]

    await w.send(press(w.hilux.id))
    assert ("answerCallbackQuery", {"callback_query_id": "q1"}) in w.api.calls
    assert "BLA 482" in w.api.last["text"] and "septembrie 2026" in w.api.last["text"]
    assert "40 000 km" in w.api.last["text"]

    await w.send(message("o sută"))
    assert w.api.last["text"] == NOT_A_NUMBER
    await w.send(message("39000"))  # sub valoarea de pornire
    assert "nu a fost înregistrată" in w.api.last["text"]

    await w.send(message("41 640 km"))
    assert w.api.texts()[-2].startswith("✅ Am înregistrat 41 640 km pentru BLA 482")
    assert "Parcurs în lună: 1 640 km" in w.api.texts()[-2]
    # rămâne Logan-ul
    remaining = w.api.last["reply_markup"]["inline_keyboard"]
    assert [row[0]["callback_data"] for row in remaining] == [f"veh:{w.logan.id}"]

    reading = await w.session.scalar(
        select(OdometerReading).where(OdometerReading.vehicle_id == w.hilux.id)
    )
    assert reading is not None
    assert (reading.year, reading.month, reading.end_odometer) == (2026, 9, 41640)
    assert (reading.source, reading.received_on, reading.entered_by) == (
        ReadingSource.TELEGRAM,
        OCT_3,
        None,
    )

    # după 10 ale lunii: luna curentă, pornind de la septembrie
    await w.send(press(w.hilux.id), today=date(2026, 10, 20))
    assert "octombrie 2026" in w.api.last["text"] and "41 640 km" in w.api.last["text"]

    # butonul unui automobil străin nu e acceptat: botul reia alegerea
    await w.send(press(w.stranger.id))
    labels = [row[0]["text"] for row in w.api.last["reply_markup"]["inline_keyboard"]]
    assert labels == ["BLA 482 · Dacia Logan ✓", "BLA 915 · Dacia Logan"]


async def test_single_vehicle_photo_and_locked_month(api: AsyncClient, w: World) -> None:
    code = await link_code(api, w, w.other)
    await w.send(message(f"/start {code}"))
    await w.send(message("/parcurs"))
    assert "CAU 301" in w.api.last["text"]  # un singur automobil: întrebat direct

    await w.send(message("", photo=[{"file_id": "x"}]))
    assert w.api.last["text"] == PHOTO

    await w.send(message("6000"))
    assert w.api.texts()[-1].startswith("✅ Am înregistrat 6 000 km")

    # adminul emite foaia pe septembrie; clientul încearcă apoi să corecteze
    issued = await api.post(
        f"/api/vehicles/{w.stranger.id}/readings/2026/9/waybill", headers=w.admin
    )
    assert issued.status_code == 201, issued.text
    # la apăsare, botul spune direct că e înscris, fără să mai ceară kilometrajul
    await w.send(message("/parcurs"))
    assert w.api.last["text"].startswith(
        "✅ Kilometrajul pentru CAU 301, luna septembrie 2026, este deja înscris: 6 000 km."
    )
    # un număr scris după aceea nu mai e luat drept kilometraj
    await w.send(message("6500"))
    assert w.api.last["text"] != LOCKED and "Transmite parcurs" in w.api.last["text"]


async def test_card_status_unlink_and_new_code(api: AsyncClient, w: World) -> None:
    status = await api.get(f"/api/clients/{w.agro.id}/telegram", headers=w.ana)
    assert status.json() == {"bot_configured": True, "link": None, "chats": []}
    # alt contabil nu vede clientul
    assert (await api.get(f"/api/clients/{w.agro.id}/telegram", headers=w.ion)).status_code == 404

    old = await link_code(api, w)
    await w.send(message(f"/start {old}"))
    chats = (await api.get(f"/api/clients/{w.agro.id}/telegram", headers=w.ana)).json()["chats"]
    assert [(c["tg_name"], c["tg_username"]) for c in chats] == [("Ion Rotaru", "ionr")]

    # codul nou: cel vechi nu mai leagă chat-uri noi
    new = await link_code(api, w)
    assert new != old
    await w.send(message(f"/start {old}", chat_id=777))
    assert "nu mai este valabil" in w.api.last["text"]

    # deconectare: chat-ul nu mai poate trimite
    resp = await api.delete(f"/api/telegram-chats/{chats[0]['id']}", headers=w.ana)
    assert resp.status_code == 200 and resp.json()["chats"] == []
    await w.send(message(SEND_BUTTON))
    assert w.api.last["text"] == NOT_LINKED
    row = await w.session.scalar(select(TelegramChat).where(TelegramChat.chat_id == CHAT))
    assert row is not None and row.unlinked_by == w.ana_user.id


async def test_chat_moves_to_another_client(api: AsyncClient, w: World) -> None:
    await w.send(message(f"/start {await link_code(api, w)}"))
    await assign(w.session, w.other, w.ana_user)
    await w.send(message(f"/start {await link_code(api, w, w.other)}"))
    assert "Vinăria Codru SA" in w.api.last["text"]
    rows = (await w.session.scalars(select(TelegramChat).where(TelegramChat.chat_id == CHAT))).all()
    assert sorted((r.client_id, r.unlinked_at is None) for r in rows) == sorted(
        [(w.agro.id, False), (w.other.id, True)]
    )


async def test_issued_waybill_among_several_vehicles(api: AsyncClient, w: World) -> None:
    await w.send(message(f"/start {await link_code(api, w)}"))
    await w.send(press(w.hilux.id))
    await w.send(message("41640"))
    issued = await api.post(f"/api/vehicles/{w.hilux.id}/readings/2026/9/waybill", headers=w.admin)
    assert issued.status_code == 201, issued.text

    await w.send(message(SEND_BUTTON))
    labels = [row[0]["text"] for row in w.api.last["reply_markup"]["inline_keyboard"]]
    assert labels == ["BLA 482 · Dacia Logan ✓ înscris", "BLA 915 · Dacia Logan"]

    await w.send(press(w.hilux.id))
    locked, rest = w.api.texts()[-2:]
    assert locked.startswith("✅ Kilometrajul pentru BLA 482, luna septembrie 2026, este deja")
    assert "41 640 km" in locked and "Foaia de parcurs a fost emisă" in locked
    assert rest == "Mai aveți de transmis pentru:"
    remaining = w.api.last["reply_markup"]["inline_keyboard"]
    assert [row[0]["callback_data"] for row in remaining] == [f"veh:{w.logan.id}"]
