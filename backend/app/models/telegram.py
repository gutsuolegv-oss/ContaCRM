"""Telegram: legarea chat-urilor de clienți și starea conversației cu botul.

Legarea: în cartela clientului se generează un cod (un singur cod activ per client), trimis
clientului ca link `t.me/<bot>?start=<cod>`. La `/start <cod>`, chat-ul se leagă de client.
Un chat e legat de cel mult un client; codul se poate regenera (cel vechi nu mai merge), iar
legăturile se pot închide din cartelă.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IdMixin, TimestampMixin, str_enum


class TelegramLinkCode(IdMixin, Base):
    __tablename__ = "telegram_link_codes"

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), unique=True
    )
    code: Mapped[str] = mapped_column(String(32), unique=True)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TelegramChat(IdMixin, TimestampMixin, Base):
    """Un chat Telegram legat de un client. `unlinked_at` completat = legătură închisă
    (rândul rămâne pentru istoric). `pending_*`: automobilul și luna pentru care botul
    așteaptă odometrul."""

    __tablename__ = "telegram_chats"
    __table_args__ = (
        Index(
            "uq_telegram_chats_chat_active",
            "chat_id",
            unique=True,
            postgresql_where=text("unlinked_at IS NULL"),
        ),
        CheckConstraint(
            "(pending_vehicle_id IS NULL) = (pending_year IS NULL)"
            " AND (pending_year IS NULL) = (pending_month IS NULL)",
            name="pending_complete",
        ),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    chat_id: Mapped[int] = mapped_column(BigInteger)
    tg_name: Mapped[str | None] = mapped_column(String(255))  # numele din Telegram
    tg_username: Mapped[str | None] = mapped_column(String(64))
    unlinked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    unlinked_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    pending_vehicle_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("vehicles.id", ondelete="RESTRICT")
    )
    pending_year: Mapped[int | None] = mapped_column(Integer)
    pending_month: Mapped[int | None] = mapped_column(Integer)


class BotStatus(enum.StrEnum):
    NOT_CONFIGURED = "not_configured"  # fără token
    PENDING = "pending"  # token nou, procesul botului încă nu l-a verificat
    CONNECTED = "connected"
    ERROR = "error"  # tokenul nu e acceptat de Telegram sau Telegram nu răspunde


class TelegramBot(IdMixin, TimestampMixin, Base):
    """Configurația botului (un singur rând). Tokenul e criptat (app.core.secrets) și nu iese
    niciodată din API; numele și starea le scrie procesul botului după ce vorbește cu Telegram.
    `checked_at` se actualizează periodic: dacă e vechi, procesul botului nu rulează."""

    __tablename__ = "telegram_bot"

    token_encrypted: Mapped[str | None] = mapped_column(Text)
    token_hint: Mapped[str | None] = mapped_column(String(8))  # ultimele caractere, pentru afișare
    username: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[BotStatus] = mapped_column(
        str_enum(BotStatus, "bot_status"),
        default=BotStatus.NOT_CONFIGURED,
        server_default=BotStatus.NOT_CONFIGURED.value,
    )
    status_message: Mapped[str | None] = mapped_column(String(255))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
