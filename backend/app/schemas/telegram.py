"""Schemele API pentru legarea clienților de Telegram."""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.models import BotStatus
from app.schemas.common import InputModel, ORMModel


class TelegramChatOut(ORMModel):
    id: int
    tg_name: str | None
    tg_username: str | None
    created_at: datetime  # când s-a legat


class TelegramStatusOut(ORMModel):
    bot_configured: bool  # botul e conectat (are nume): altfel nu se poate forma linkul
    link: str | None  # t.me/<bot>?start=<cod>; None dacă nu s-a generat încă
    chats: list[TelegramChatOut]


# Tokenul de la @BotFather: <id bot>:<cheie>
BotToken = Annotated[
    str,
    StringConstraints(strip_whitespace=True, pattern=r"^\d{5,15}:[A-Za-z0-9_-]{30,60}$"),
]


class BotTokenIn(InputModel):
    """`token` null: botul se oprește (tokenul se șterge)."""

    token: BotToken | None


class BotSettingsOut(BaseModel):
    configured: bool  # există un token
    token_hint: str | None  # ultimele caractere ale tokenului; tokenul întreg nu iese niciodată
    username: str | None  # aflat de procesul botului de la Telegram
    status: BotStatus
    status_message: str | None
    checked_at: datetime | None
    running: bool  # procesul botului a dat semn de viață recent
