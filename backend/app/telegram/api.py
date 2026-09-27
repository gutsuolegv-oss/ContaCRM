"""Clientul pentru Telegram Bot API (doar ce folosește botul)."""

from typing import Any, Protocol

import httpx


class TelegramError(Exception):
    """Telegram a răspuns cu `ok: false` (`status` = codul HTTP, ex. 401 token respins) sau
    cererea nu a ajuns la Telegram (`status` None)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BotApi(Protocol):
    async def call(self, method: str, **params: Any) -> Any: ...


class HttpBotApi:
    """Apeluri HTTPS spre api.telegram.org. Tokenul nu apare în mesajele de eroare."""

    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=f"https://api.telegram.org/bot{token}/",
            # getUpdates ține conexiunea deschisă până la 30 s (long polling)
            timeout=httpx.Timeout(10.0, read=40.0),
        )

    async def call(self, method: str, **params: Any) -> Any:
        payload = {k: v for k, v in params.items() if v is not None}
        try:
            resp = await self._client.post(method, json=payload)
        except httpx.HTTPError as e:
            raise TelegramError(f"{method}: {type(e).__name__}") from None
        data = (
            resp.json()
            if resp.headers.get("content-type", "").startswith("application/json")
            else {}
        )
        if not data.get("ok"):
            raise TelegramError(
                f"{method}: {resp.status_code} {data.get('description', '')}", resp.status_code
            )
        return data["result"]

    async def aclose(self) -> None:
        await self._client.aclose()
