from datetime import date
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, Status, StatusSet, User, UserRole
from app.seed.classifier import seed_classifier
from app.services.matrix import MatrixService
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import assign, make_client

SEPT = {"year": 2026, "month": 9}
AUG = {"year": 2026, "month": 8}


class World:
    admin: dict[str, str]
    ana: dict[str, str]
    ana_user: User
    mine: Client
    other: Client


@pytest.fixture
async def world(session: AsyncSession, auth: AuthHeaders) -> World:
    await seed_classifier(session)
    w = World()
    admin_user, w.admin = await auth(UserRole.ADMIN)
    w.ana_user, w.ana = await auth(UserRole.CONTABIL)
    w.mine = await make_client(session, "1003600012345", name="Agro-Nord SRL", is_vat_payer=True)
    w.other = await make_client(session, "1002600054321", name="Vinăria Codru SA")
    await assign(session, w.mine, w.ana_user)
    for firm in (w.mine, w.other):
        await MatrixService(session, admin_user).apply(firm, date(2026, 1, 1))
    return w


async def status_id(session: AsyncSession, set_code: str, code: str) -> int:
    found = await session.scalar(
        select(Status.id).join(StatusSet).where(StatusSet.code == set_code, Status.code == code)
    )
    assert found is not None
    return found


def cell(grid: dict[str, Any], client: Client, code: str) -> dict[str, Any]:
    rt_id = next(rt["id"] for rt in grid["report_types"] if rt["code"] == code)
    row = next(r for r in grid["rows"] if r["client"]["id"] == client.id)
    found: dict[str, Any] = next(e for e in row["entries"] if e["report_type_id"] == rt_id)
    return found


async def test_generate_and_view(api: AsyncClient, world: World) -> None:
    denied = await api.post("/api/grid/generate", params=SEPT, headers=world.ana)
    assert denied.status_code == 403
    resp = await api.post("/api/grid/generate", params=SEPT, headers=world.admin)
    assert resp.status_code == 200, resp.text
    # Agro-Nord: TVA12 + 3 documente; Vinăria: 3 documente
    assert resp.json()["created"] == 7
    assert [p["period"]["period_type"] for p in resp.json()["periods"]] == [
        "lunar",
        "trimestrial",
    ]

    grid = (await api.get("/api/grid", params=SEPT, headers=world.admin)).json()
    assert [r["client"]["name"] for r in grid["rows"]] == ["Agro-Nord SRL", "Vinăria Codru SA"]
    assert [rt["code"] for rt in grid["report_types"]] == [
        "TVA12", "FACT_LIVR", "FACT_PROC", "EXTRASE",
    ]  # fmt: skip
    tva = cell(grid, world.mine, "TVA12")
    assert tva["deadline"] == "2026-10-26"
    assert tva["is_overdue"] is False
    assert tva["steps"][0]["status"]["code"] == "neinceput"


async def test_contabil_sees_own_clients_only(api: AsyncClient, world: World) -> None:
    await api.post("/api/grid/generate", params=SEPT, headers=world.admin)
    grid = (await api.get("/api/grid", params=SEPT, headers=world.ana)).json()
    assert [r["client"]["id"] for r in grid["rows"]] == [world.mine.id]
    # cererea explicită a altui client nu-l face vizibil
    other = await api.get(
        "/api/grid", params={**SEPT, "client_id": world.other.id}, headers=world.ana
    )
    assert other.json()["rows"] == []


async def test_contabil_works_on_cells(
    api: AsyncClient, session: AsyncSession, world: World
) -> None:
    await api.post("/api/grid/generate", params=SEPT, headers=world.admin)
    grid = (await api.get("/api/grid", params=SEPT, headers=world.ana)).json()
    tva = cell(grid, world.mine, "TVA12")
    step_id = tva["steps"][0]["step_id"]

    resp = await api.put(
        f"/api/grid/entries/{tva['id']}/steps/{step_id}",
        json={"status_id": await status_id(session, "depunere", "incarcat")},
        headers=world.ana,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["is_completed"] is True
    assert resp.json()["steps"][0]["changed_by"] == world.ana_user.id

    notes = await api.patch(
        f"/api/grid/entries/{tva['id']}", json={"notes": "depus pe 20.10"}, headers=world.ana
    )
    assert notes.json()["notes"] == "depus pe 20.10"
    deadline = await api.patch(
        f"/api/grid/entries/{tva['id']}", json={"deadline": "2026-11-01"}, headers=world.ana
    )
    assert deadline.status_code == 403

    wrong_set = await api.put(
        f"/api/grid/entries/{tva['id']}/steps/{step_id}",
        json={"status_id": await status_id(session, "binar", "efectuat")},
        headers=world.ana,
    )
    assert wrong_set.status_code == 422

    open_only = await api.get("/api/grid", params={**SEPT, "only_open": True}, headers=world.ana)
    codes = {rt["id"]: rt["code"] for rt in open_only.json()["report_types"]}
    assert "TVA12" not in codes.values()


async def test_other_accountants_cells_hidden(
    api: AsyncClient, auth: AuthHeaders, world: World
) -> None:
    await api.post("/api/grid/generate", params=SEPT, headers=world.admin)
    grid = (await api.get("/api/grid", params=SEPT, headers=world.admin)).json()
    extrase = cell(grid, world.other, "EXTRASE")
    resp = await api.get(f"/api/grid/entries/{extrase['id']}", headers=world.ana)
    assert resp.status_code == 404


async def test_overdue_filter(api: AsyncClient, world: World) -> None:
    # august: termenul TVA12 e 25.09.2026 (vineri); „azi” e 27.09 → întârziat
    await api.post("/api/grid/generate", params=AUG, headers=world.admin)
    overdue = (
        await api.get("/api/grid", params={**AUG, "only_overdue": True}, headers=world.admin)
    ).json()
    assert [rt["code"] for rt in overdue["report_types"]] == ["TVA12"]
    assert cell(overdue, world.mine, "TVA12")["is_overdue"] is True


async def test_close_and_reopen_period(
    api: AsyncClient, session: AsyncSession, world: World
) -> None:
    gen = (await api.post("/api/grid/generate", params=SEPT, headers=world.admin)).json()
    period_id = gen["periods"][0]["period"]["id"]
    assert (
        await api.post(f"/api/grid/periods/{period_id}/close", headers=world.ana)
    ).status_code == 403
    closed = await api.post(f"/api/grid/periods/{period_id}/close", headers=world.admin)
    assert closed.json()["is_closed"] is True

    grid = (await api.get("/api/grid", params=SEPT, headers=world.ana)).json()
    tva = cell(grid, world.mine, "TVA12")
    resp = await api.put(
        f"/api/grid/entries/{tva['id']}/steps/{tva['steps'][0]['step_id']}",
        json={"status_id": await status_id(session, "depunere", "transmis")},
        headers=world.ana,
    )
    assert resp.status_code == 409
    await api.post(f"/api/grid/periods/{period_id}/reopen", headers=world.admin)
    resp = await api.put(
        f"/api/grid/entries/{tva['id']}/steps/{tva['steps'][0]['step_id']}",
        json={"status_id": await status_id(session, "depunere", "transmis")},
        headers=world.ana,
    )
    assert resp.status_code == 200


@pytest.mark.parametrize("params", [{"year": 2026, "month": 13}, {"year": 2026}, {"month": 9}])
async def test_query_validation(api: AsyncClient, world: World, params: dict[str, int]) -> None:
    assert (await api.get("/api/grid", params=params, headers=world.admin)).status_code == 422


async def test_empty_month(api: AsyncClient, world: World) -> None:
    grid = await api.get("/api/grid", params={"year": 2030, "month": 1}, headers=world.admin)
    assert grid.status_code == 200
    assert grid.json()["periods"] == grid.json()["rows"] == []
