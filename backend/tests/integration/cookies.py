"""Ajutor pentru teste: refresh token-ul vine în cookie-ul httpOnly, nu în JSON."""

from typing import Any

from httpx import AsyncClient, Response

from app.api.auth import REFRESH_COOKIE


def refresh_token_of(resp: Response) -> str:
    token = resp.cookies.get(REFRESH_COOKIE)
    assert token, "răspunsul nu a setat cookie-ul de sesiune"
    return token


async def login_with_cookie(client: AsyncClient, username: str, password: str) -> dict[str, Any]:
    """Login; întoarce JSON-ul plus `refresh_token` citit din cookie."""
    resp = await client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    data: dict[str, Any] = resp.json()
    assert "refresh_token" not in data
    return data | {"refresh_token": refresh_token_of(resp)}


async def post_with_refresh(client: AsyncClient, path: str, token: str) -> Response:
    """POST la /api/auth/* cu exact acest refresh token în cookie (ca un browser care îl are)."""
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, token)
    return await client.post(path)
