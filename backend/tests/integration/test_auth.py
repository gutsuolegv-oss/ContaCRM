from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated

import pytest
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.security import create_access_token, hash_password, hash_token
from app.db.base import RecordStatus
from app.db.session import get_session
from app.main import create_app
from app.models import Organization, RefreshToken, User, UserRole

PASSWORD = "parola-corecta-123"  # noqa: S105

MakeUser = Callable[..., Awaitable[User]]


@pytest.fixture
async def make_user(session: AsyncSession) -> MakeUser:
    org = Organization(name="Birou")
    session.add(org)
    await session.flush()

    async def _make(email: str = "ana@birou.md", role: UserRole = UserRole.CONTABIL) -> User:
        user = User(
            organization_id=org.id,
            email=email,
            full_name="Ana",
            password_hash=hash_password(PASSWORD),
            role=role,
        )
        session.add(user)
        await session.flush()
        return user

    return _make


async def _login(client: AsyncClient, email: str = "ana@birou.md") -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    data: dict[str, str] = resp.json()
    return data


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_login_and_me(client: AsyncClient, make_user: MakeUser) -> None:
    user = await make_user()
    tokens = await _login(client)
    assert tokens["token_type"] == "bearer"  # noqa: S105
    resp = await client.get("/api/auth/me", headers=_bearer(tokens["access_token"]))
    assert resp.status_code == 200
    assert resp.json() == {
        "id": user.id,
        "email": "ana@birou.md",
        "full_name": "Ana",
        "role": "contabil",
        "must_change_password": False,
    }
    assert user.last_login_at is not None


async def test_login_email_case_insensitive(client: AsyncClient, make_user: MakeUser) -> None:
    await make_user()
    await _login(client, " ANA@Birou.md ")


async def test_refresh_token_stored_only_as_hash(
    client: AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    await make_user()
    tokens = await _login(client)
    stored = (await session.scalars(select(RefreshToken.token_hash))).all()
    assert stored == [hash_token(tokens["refresh_token"])]


@pytest.mark.parametrize(
    ("email", "password"),
    [("ana@birou.md", "gresita"), ("nimeni@birou.md", PASSWORD)],
)
async def test_login_rejected_with_same_message(
    client: AsyncClient, make_user: MakeUser, email: str, password: str
) -> None:
    await make_user()
    resp = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Email sau parolă greșită"


async def test_archived_user_cannot_login(client: AsyncClient, make_user: MakeUser) -> None:
    user = await make_user()
    user.status = RecordStatus.ARCHIVED
    user.deleted_at = datetime.now(UTC)
    resp = await client.post(
        "/api/auth/login", json={"email": "ana@birou.md", "password": PASSWORD}
    )
    assert resp.status_code == 401


async def test_archived_user_access_token_stops_working(
    client: AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    user = await make_user()
    tokens = await _login(client)
    user.status = RecordStatus.ARCHIVED
    user.deleted_at = datetime.now(UTC)
    await session.flush()
    resp = await client.get("/api/auth/me", headers=_bearer(tokens["access_token"]))
    assert resp.status_code == 401


@pytest.mark.parametrize("header", [None, "Bearer nu-e-jwt", "Basic abc"])
async def test_me_requires_valid_token(client: AsyncClient, header: str | None) -> None:
    headers = {"Authorization": header} if header else {}
    resp = await client.get("/api/auth/me", headers=headers)
    assert resp.status_code == 401


async def test_expired_access_token(client: AsyncClient, make_user: MakeUser) -> None:
    user = await make_user()
    token = create_access_token(user.id, datetime.now(UTC) - timedelta(hours=1))
    resp = await client.get("/api/auth/me", headers=_bearer(token))
    assert resp.status_code == 401


async def test_refresh_token_is_not_an_access_token(
    client: AsyncClient, make_user: MakeUser
) -> None:
    await make_user()
    tokens = await _login(client)
    resp = await client.get("/api/auth/me", headers=_bearer(tokens["refresh_token"]))
    assert resp.status_code == 401


async def test_refresh_rotates_token(client: AsyncClient, make_user: MakeUser) -> None:
    await make_user()
    first = await _login(client)
    resp = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert resp.status_code == 200
    second = resp.json()
    assert second["refresh_token"] != first["refresh_token"]
    me = await client.get("/api/auth/me", headers=_bearer(second["access_token"]))
    assert me.status_code == 200


async def test_reused_refresh_token_revokes_all_sessions(
    client: AsyncClient, make_user: MakeUser
) -> None:
    await make_user()
    first = await _login(client)
    second = (
        await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()
    # Tokenul vechi folosit din nou: refuzat, și se închide și sesiunea nouă.
    reuse = await client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert reuse.status_code == 401
    after = await client.post("/api/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert after.status_code == 401


async def test_expired_refresh_token(
    client: AsyncClient, session: AsyncSession, make_user: MakeUser
) -> None:
    await make_user()
    tokens = await _login(client)
    stored = await session.scalar(select(RefreshToken))
    assert stored is not None
    stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await session.flush()
    resp = await client.post("/api/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert resp.status_code == 401


async def test_logout_revokes_refresh_token(client: AsyncClient, make_user: MakeUser) -> None:
    await make_user()
    tokens = await _login(client)
    body = {"refresh_token": tokens["refresh_token"]}
    assert (await client.post("/api/auth/logout", json=body)).status_code == 204
    assert (await client.post("/api/auth/refresh", json=body)).status_code == 401
    # Logout repetat sau cu token necunoscut nu dă eroare.
    assert (await client.post("/api/auth/logout", json=body)).status_code == 204


async def test_require_roles(session: AsyncSession, make_user: MakeUser) -> None:
    app = create_app()

    @app.get("/_doar-admin")
    async def _admin_only(
        user: Annotated[User, Depends(require_roles(UserRole.ADMIN))],
    ) -> dict[str, int]:
        return {"id": user.id}

    async def _override() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _override
    await make_user("admin@birou.md", UserRole.ADMIN)
    await make_user("ana@birou.md", UserRole.CONTABIL)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        admin = await _login(ac, "admin@birou.md")
        contabil = await _login(ac, "ana@birou.md")
        ok = await ac.get("/_doar-admin", headers=_bearer(admin["access_token"]))
        denied = await ac.get("/_doar-admin", headers=_bearer(contabil["access_token"]))
        anon = await ac.get("/_doar-admin")
    assert ok.status_code == 200
    assert denied.status_code == 403
    assert anon.status_code == 401
