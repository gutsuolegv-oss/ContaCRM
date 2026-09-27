"""/api — legarea clientului de Telegram (linkul personal pentru bot și chat-urile legate).

Aceleași drepturi ca la cartela clientului: contabilul doar pe clienții repartizați lui.
"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.core.clock import utc_now
from app.schemas.telegram import TelegramStatusOut
from app.services.telegram import TelegramLinkService

router = APIRouter(tags=["telegram"])


@router.get("/api/clients/{client_id}/telegram", response_model=TelegramStatusOut)
async def telegram_status(
    client_id: int, session: SessionDep, user: CurrentUser
) -> TelegramStatusOut:
    return await TelegramLinkService(session, user).status(client_id)


@router.post("/api/clients/{client_id}/telegram/link", response_model=TelegramStatusOut)
async def regenerate_link(
    client_id: int, session: SessionDep, user: CurrentUser
) -> TelegramStatusOut:
    """Link nou pentru client; cel vechi nu mai leagă chat-uri noi (cele legate rămân)."""
    return await TelegramLinkService(session, user).regenerate_code(client_id)


@router.delete("/api/telegram-chats/{chat_row_id}", response_model=TelegramStatusOut)
async def unlink_chat(
    chat_row_id: int, session: SessionDep, user: CurrentUser
) -> TelegramStatusOut:
    """Chat-ul nu mai poate trimite date pentru client; rămâne în istoric."""
    return await TelegramLinkService(session, user).unlink(chat_row_id, utc_now())
