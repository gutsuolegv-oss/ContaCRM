"""Schemele API pentru legarea clienților de Telegram."""

from datetime import datetime, time
from typing import Annotated, Self

from pydantic import BaseModel, Field, StringConstraints, field_validator, model_validator

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
    auto_reminders: bool  # reamintirile automate pentru odometru
    reminder_weekdays: list[int]  # 1 = luni … 7 = duminică
    reminder_from: time
    reminder_to: time


class ReminderSettingsIn(InputModel):
    """Reamintirile pentru odometru: cele automate pornite sau nu și intervalul în care pleacă
    toate (automate și manuale)."""

    auto_reminders: bool
    weekdays: Annotated[list[Annotated[int, Field(ge=1, le=7)]], Field(min_length=1, max_length=7)]
    start: time
    end: time

    @field_validator("weekdays")
    @classmethod
    def _unique_sorted(cls, v: list[int]) -> list[int]:
        return sorted(set(v))

    @model_validator(mode="after")
    def _window(self) -> Self:
        if self.start >= self.end:
            raise ValueError("ora de început trebuie să fie înaintea celei de sfârșit")
        return self
