"""Telegram: legarea chat-urilor de clienți și starea conversației cu botul.

Legarea: în cartela clientului se generează un cod (un singur cod activ per client), trimis
clientului ca link `t.me/<bot>?start=<cod>`. La `/start <cod>`, chat-ul se leagă de client.
Un chat e legat de cel mult un client; codul se poate regenera (cel vechi nu mai merge), iar
legăturile se pot închide din cartelă.
"""

import enum
from datetime import datetime, time

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
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
    __table_args__ = (
        CheckConstraint("reminder_from < reminder_to", name="reminder_window"),
        CheckConstraint(
            "cardinality(reminder_weekdays) > 0 AND reminder_weekdays <@ '{1,2,3,4,5,6,7}'",
            name="reminder_weekdays_valid",
        ),
    )

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
    # Reamintirile automate pentru odometru (ultima zi a lunii 15:00, apoi pe 3 la 10:00).
    auto_reminders: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Intervalul în care pleacă reamintirile (automate și manuale); în afara lui așteaptă.
    # Zilele: 1 = luni … 7 = duminică (ISO).
    reminder_weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{1,2,3,4,5}'")
    )
    reminder_from: Mapped[time] = mapped_column(Time, server_default=text("'09:00'"))
    reminder_to: Mapped[time] = mapped_column(Time, server_default=text("'18:00'"))
    updated_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )


class ReminderKind(enum.StrEnum):
    AUTO_REQUEST = "auto_request"  # ultima zi a lunii: „transmiteți kilometrajul”
    AUTO_REMINDER = "auto_reminder"  # pe 3 ale lunii următoare, dacă tot lipsesc date
    MANUAL = "manual"  # trimisă de contabil din aplicație


class ReminderStatus(enum.StrEnum):
    QUEUED = "queued"  # așteaptă procesul botului
    SENT = "sent"  # ajunsă la cel puțin un chat
    SKIPPED = "skipped"  # nu mai era nimic de cerut sau clientul nu are chat legat
    FAILED = "failed"  # Telegram a refuzat toate chat-urile (ex. botul blocat)


class FleetReminder(IdMixin, Base):
    """O reamintire pe Telegram către un client, pentru odometrul automobilelor pe o lună.
    Cele automate sunt unice pe client, lună și tip (nu se trimit de două ori)."""

    __tablename__ = "fleet_reminders"
    __table_args__ = (
        Index(
            "uq_fleet_reminders_auto",
            "client_id",
            "year",
            "month",
            "kind",
            unique=True,
            postgresql_where=text("kind <> 'manual'"),
        ),
        CheckConstraint("month BETWEEN 1 AND 12", name="month_range"),
    )

    client_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("clients.id", ondelete="RESTRICT"), index=True
    )
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    kind: Mapped[ReminderKind] = mapped_column(str_enum(ReminderKind, "reminder_kind"))
    status: Mapped[ReminderStatus] = mapped_column(
        str_enum(ReminderStatus, "reminder_status"),
        default=ReminderStatus.QUEUED,
        server_default=ReminderStatus.QUEUED.value,
    )
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    chats: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # chat-uri atinse
    vehicles: Mapped[int] = mapped_column(Integer, server_default=text("0"))  # automobile cerute
    note: Mapped[str | None] = mapped_column(String(255))  # de ce a fost sărită / a eșuat
