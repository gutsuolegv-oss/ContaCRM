from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PASSWORD_CHANGE_REQUIRED
from app.core.security import hash_password
from app.models import AuditLog, ClientAssignment, User, UserRole
from tests.integration.cookies import login_with_cookie, post_with_refresh
from tests.integration.factories import assign, make_client, make_user

ADMIN_PW = "parola-admin-12345"
INITIAL_PW = "parola-initiala-1"
NEW_PW = "parola-noua-ana-2026"


async def login(api: AsyncClient, username: str, password: str) -> dict[str, Any]:
    return await login_with_cookie(api, username, password)


def bearer(tokens: dict[str, Any]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    return await make_user(session, "admin", UserRole.ADMIN, password_hash=hash_password(ADMIN_PW))


@pytest.fixture
async def admin_h(api: AsyncClient, admin: User) -> dict[str, str]:
    return bearer(await login(api, admin.username, ADMIN_PW))


async def create_ana(api: AsyncClient, admin_h: dict[str, str]) -> dict[str, Any]:
    resp = await api.post(
        "/api/users",
        json={
            "username": " Ana ",
            "full_name": "Ana Rusu",
            "role": "contabil",
            "password": INITIAL_PW,
        },
        headers=admin_h,
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_create_user(api: AsyncClient, admin_h: dict[str, str]) -> None:
    ana = await create_ana(api, admin_h)
    assert ana["username"] == "ana"
    assert ana["must_change_password"] is True
    assert "password" not in str(ana).replace("must_change_password", "")

    dup = await api.post(
        "/api/users",
        json={
            "username": "ANA",
            "full_name": "X",
            "role": "contabil",
            "password": INITIAL_PW,
        },
        headers=admin_h,
    )
    assert dup.status_code == 409
    for bad in ({"password": "scurta"}, {"username": "cu spațiu"}, {"role": "superuser"}):
        body = {
            "username": "xx",
            "full_name": "X",
            "role": "contabil",
            "password": INITIAL_PW,
        } | bad
        assert (await api.post("/api/users", json=body, headers=admin_h)).status_code == 422


@pytest.mark.parametrize("role", [UserRole.DIRECTOR, UserRole.CONTABIL])
async def test_only_admin_manages(
    api: AsyncClient, session: AsyncSession, admin: User, role: UserRole
) -> None:
    await make_user(session, "xx", role, password_hash=hash_password(ADMIN_PW))
    headers = bearer(await login(api, "xx", ADMIN_PW))
    body = {"username": "yy", "full_name": "Y", "role": "contabil", "password": INITIAL_PW}
    assert (await api.post("/api/users", json=body, headers=headers)).status_code == 403
    listing = await api.get("/api/users", headers=headers)
    assert listing.status_code == (200 if role is UserRole.DIRECTOR else 403)


async def test_first_login_must_change_password(api: AsyncClient, admin_h: dict[str, str]) -> None:
    await create_ana(api, admin_h)
    first = await login(api, "ana", INITIAL_PW)

    me = await api.get("/api/auth/me", headers=bearer(first))
    assert me.status_code == 200 and me.json()["must_change_password"] is True
    blocked = await api.get("/api/clients", headers=bearer(first))
    assert (blocked.status_code, blocked.json()["detail"]) == (403, PASSWORD_CHANGE_REQUIRED)

    wrong = await api.post(
        "/api/auth/change-password",
        json={"current_password": "gresita-gresita", "new_password": NEW_PW},
        headers=bearer(first),
    )
    assert wrong.status_code == 422
    same = await api.post(
        "/api/auth/change-password",
        json={"current_password": INITIAL_PW, "new_password": INITIAL_PW},
        headers=bearer(first),
    )
    assert same.status_code == 422

    changed = await api.post(
        "/api/auth/change-password",
        json={"current_password": INITIAL_PW, "new_password": NEW_PW},
        headers=bearer(first),
    )
    assert changed.status_code == 200, changed.text
    # sesiunea veche e închisă imediat (access și refresh), cea nouă merge
    assert (await api.get("/api/auth/me", headers=bearer(first))).status_code == 401
    refresh = await post_with_refresh(api, "/api/auth/refresh", first["refresh_token"])
    assert refresh.status_code == 401
    assert (await api.get("/api/clients", headers=bearer(changed.json()))).status_code == 200
    await login(api, "ana", NEW_PW)


async def test_admin_reset_closes_sessions(api: AsyncClient, admin_h: dict[str, str]) -> None:
    ana = await create_ana(api, admin_h)
    tokens = await login(api, "ana", INITIAL_PW)
    reset = await api.post(
        f"/api/users/{ana['id']}/reset-password",
        json={"password": "alta-parola-12345"},
        headers=admin_h,
    )
    assert reset.json()["must_change_password"] is True
    assert (await api.get("/api/auth/me", headers=bearer(tokens))).status_code == 401
    refresh = await post_with_refresh(api, "/api/auth/refresh", tokens["refresh_token"])
    assert refresh.status_code == 401
    old = await api.post("/api/auth/login", json={"username": "ana", "password": INITIAL_PW})
    assert old.status_code == 401
    await login(api, "ana", "alta-parola-12345")


async def test_archive_accountant(
    api: AsyncClient, session: AsyncSession, admin: User, admin_h: dict[str, str]
) -> None:
    ana_out = await create_ana(api, admin_h)
    ana = await session.get(User, ana_out["id"])
    assert ana is not None
    firm = await make_client(session)
    await assign(session, firm, ana)

    resp = await api.delete(f"/api/users/{ana.id}", headers=admin_h)
    assert resp.status_code == 200 and resp.json()["status"] == "archived"
    login_after = await api.post(
        "/api/auth/login", json={"username": "ana", "password": INITIAL_PW}
    )
    assert login_after.status_code == 401
    assignment = (
        await session.scalars(select(ClientAssignment).where(ClientAssignment.user_id == ana.id))
    ).one()
    await session.refresh(assignment)
    assert assignment.unassigned_at is not None
    assert assignment.unassigned_by == admin.id

    active = await api.get("/api/users", headers=admin_h)
    assert [u["username"] for u in active.json()] == ["admin"]
    everyone = await api.get("/api/users", params={"include_archived": True}, headers=admin_h)
    assert len(everyone.json()) == 2
    # numele de utilizator se poate refolosi
    await create_ana(api, admin_h)


async def test_last_admin_protected(api: AsyncClient, admin: User, admin_h: dict[str, str]) -> None:
    assert (await api.delete(f"/api/users/{admin.id}", headers=admin_h)).status_code == 409
    demote = await api.patch(f"/api/users/{admin.id}", json={"role": "director"}, headers=admin_h)
    assert demote.status_code == 409

    second = await api.post(
        "/api/users",
        json={
            "username": "admin2",
            "full_name": "Admin 2",
            "role": "admin",
            "password": INITIAL_PW,
        },
        headers=admin_h,
    )
    demote = await api.patch(f"/api/users/{admin.id}", json={"role": "director"}, headers=admin_h)
    assert demote.status_code == 200
    # ca director, nu mai administrează conturi
    denied = await api.delete(f"/api/users/{second.json()['id']}", headers=admin_h)
    assert denied.status_code == 403


async def test_audit_never_contains_password(
    api: AsyncClient, session: AsyncSession, admin_h: dict[str, str]
) -> None:
    ana = await create_ana(api, admin_h)
    await api.post(
        f"/api/users/{ana['id']}/reset-password",
        json={"password": "alta-parola-12345"},
        headers=admin_h,
    )
    rows = (
        await session.scalars(
            select(AuditLog).where(AuditLog.entity_type == "users").order_by(AuditLog.id)
        )
    ).all()
    assert len(rows) == 2
    for row in rows:
        values = {**(row.old_values or {}), **(row.new_values or {})}
        assert "password_hash" not in values
    # contul nou avea deja must_change_password = true: se schimbă doar versiunea sesiunii
    assert rows[1].new_values == {"session_version": 1}
