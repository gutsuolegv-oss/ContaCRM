"""Parcul auto: automobile, odometrul lunar, foi de parcurs („azi” = 27.09.2026)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLog, Client, UserRole
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import assign, make_client

HILUX: dict[str, Any] = {
    "plate": " bla  482 ",
    "model": "Toyota Hilux",
    "fuel_type": "motorina",
    "fuel_norm": "9.8",
    "driver": "Ion Rotaru",
    "initial_odometer": 40000,
}


class Setup:
    client: Client
    ana: dict[str, str]  # contabilul clientului
    ion: dict[str, str]  # alt contabil
    admin: dict[str, str]


@pytest.fixture
async def s(session: AsyncSession, auth: AuthHeaders) -> Setup:
    setup = Setup()
    setup.client = await make_client(session, name="Agro-Nord SRL", has_transport=True)
    ana_user, setup.ana = await auth(UserRole.CONTABIL)
    _, setup.ion = await auth(UserRole.CONTABIL)
    _, setup.admin = await auth(UserRole.ADMIN)
    await assign(session, setup.client, ana_user)
    return setup


async def add_vehicle(api: AsyncClient, s: Setup, **kw: Any) -> dict[str, Any]:
    resp = await api.post(
        f"/api/clients/{s.client.id}/vehicles", json={**HILUX, **kw}, headers=s.ana
    )
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def put_reading(
    api: AsyncClient, s: Setup, vehicle_id: int, month: int, value: int, year: int = 2026
) -> Any:
    return await api.put(
        f"/api/vehicles/{vehicle_id}/readings/{year}/{month}",
        json={"end_odometer": value, "source": "email", "received_on": "2026-09-27"},
        headers=s.ana,
    )


async def fleet(api: AsyncClient, s: Setup, month: int) -> dict[str, Any]:
    resp = await api.get(
        f"/api/clients/{s.client.id}/fleet",
        params={"year": 2026, "month": month},
        headers=s.ana,
    )
    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def test_vehicle_crud_and_access(api: AsyncClient, s: Setup) -> None:
    v = await add_vehicle(api, s)
    assert (v["plate"], v["fuel_norm"]) == ("BLA 482", 9.8)

    dup = await api.post(
        f"/api/clients/{s.client.id}/vehicles", json={**HILUX, "plate": "BLA 482"}, headers=s.admin
    )
    assert dup.status_code == 409
    bad = await api.post(
        f"/api/clients/{s.client.id}/vehicles", json={**HILUX, "plate": "BLĂ!"}, headers=s.ana
    )
    assert bad.status_code == 422

    # alt contabil nu vede nimic
    assert (await api.get(f"/api/clients/{s.client.id}/vehicles", headers=s.ion)).status_code == 404
    patch = await api.patch(f"/api/vehicles/{v['id']}", json={"driver": "X"}, headers=s.ion)
    assert patch.status_code == 404

    ok = await api.patch(f"/api/vehicles/{v['id']}", json={"fuel_norm": 10.5}, headers=s.ana)
    assert ok.json()["fuel_norm"] == 10.5

    assert (await api.delete(f"/api/vehicles/{v['id']}", headers=s.ana)).status_code == 204
    listed = await api.get(f"/api/clients/{s.client.id}/vehicles", headers=s.ana)
    assert listed.json() == []
    # după scoaterea din evidență, numărul se poate lua din nou
    await add_vehicle(api, s)


async def test_month_statuses_and_readings(api: AsyncClient, s: Setup) -> None:
    v = await add_vehicle(api, s)

    aug = await fleet(api, s, 8)
    assert aug["deadline"] == "2026-08-31"
    assert [(r["status"], r["start_odometer"]) for r in aug["rows"]] == [("late", 40000)]
    assert (await fleet(api, s, 9))["rows"][0]["status"] == "waiting"

    assert (await put_reading(api, s, v["id"], 8, 41640)).status_code == 200
    row = (await fleet(api, s, 8))["rows"][0]
    assert (row["status"], row["km"], row["fuel_liters"]) == ("received", 1640, 160.72)
    assert (await fleet(api, s, 9))["rows"][0]["start_odometer"] == 41640

    # sub început, lună viitoare, peste luna următoare
    assert (await put_reading(api, s, v["id"], 9, 41000)).status_code == 422
    assert (await put_reading(api, s, v["id"], 10, 42000)).status_code == 422
    assert (await put_reading(api, s, v["id"], 9, 42500)).status_code == 200
    assert (await put_reading(api, s, v["id"], 8, 43000)).status_code == 422
    # corectare
    assert (await put_reading(api, s, v["id"], 8, 41700)).status_code == 200
    assert (await fleet(api, s, 9))["rows"][0]["km"] == 800

    # odometrul inițial nu se mai schimbă după prima citire
    resp = await api.patch(f"/api/vehicles/{v['id']}", json={"initial_odometer": 1}, headers=s.ana)
    assert resp.status_code == 422

    gone = await api.delete(f"/api/vehicles/{v['id']}/readings/2026/9", headers=s.ana)
    assert gone.status_code == 204
    assert (await fleet(api, s, 9))["rows"][0]["status"] == "waiting"


async def test_waybills(api: AsyncClient, s: Setup, session: AsyncSession) -> None:
    v = await add_vehicle(api, s)
    other = await add_vehicle(api, s, plate="BLA 915", fuel_type="benzina", fuel_norm=7.2)
    no_data = await api.post(f"/api/vehicles/{v['id']}/readings/2026/8/waybill", headers=s.ana)
    assert no_data.status_code == 422

    await put_reading(api, s, v["id"], 8, 41640)
    await put_reading(api, s, other["id"], 8, 40500)
    await put_reading(api, s, v["id"], 9, 42000)

    one = await api.post(f"/api/vehicles/{v['id']}/readings/2026/9/waybill", headers=s.ana)
    assert one.status_code == 201, one.text
    assert one.json()["number"] == "FP-2026-09-001"
    again = await api.post(f"/api/vehicles/{v['id']}/readings/2026/9/waybill", headers=s.ana)
    assert again.status_code == 409

    batch = await api.post(f"/api/clients/{s.client.id}/fleet/2026/8/waybills", headers=s.ana)
    assert batch.status_code == 201
    by_plate = {w["plate"]: w for w in batch.json()}
    assert sorted(w["number"] for w in batch.json()) == ["FP-2026-08-001", "FP-2026-08-002"]
    hilux = by_plate["BLA 482"]
    assert (hilux["start_odometer"], hilux["end_odometer"], hilux["km"]) == (40000, 41640, 1640)
    assert (hilux["fuel_liters"], hilux["client_name"]) == (160.72, "Agro-Nord SRL")
    assert (await fleet(api, s, 8))["rows"][0]["status"] == "issued"

    # foaia păstrează valorile de la emitere
    await api.patch(f"/api/vehicles/{v['id']}", json={"fuel_norm": 20}, headers=s.ana)
    kept = await api.get(f"/api/waybills/{hilux['id']}", headers=s.ana)
    assert kept.json()["fuel_norm"] == 9.8
    assert (await api.get(f"/api/waybills/{hilux['id']}", headers=s.ion)).status_code == 404

    # blocări: citirea cu foaie și cea dinaintea unei foi
    assert (await put_reading(api, s, v["id"], 9, 42100)).status_code == 409
    assert (await put_reading(api, s, v["id"], 8, 41650)).status_code == 409

    listed = await api.get(f"/api/clients/{s.client.id}/waybills", headers=s.ana)
    assert [w["number"] for w in listed.json()] == [
        "FP-2026-09-001",
        "FP-2026-08-002",
        "FP-2026-08-001",
    ]

    # anularea deblochează corectarea și rămâne în jurnal
    cancel = await api.delete(f"/api/waybills/{one.json()['id']}", headers=s.ana)
    assert cancel.status_code == 204
    assert (await put_reading(api, s, v["id"], 9, 42100)).status_code == 200
    logged = await session.scalar(
        select(AuditLog).where(
            AuditLog.entity_type == "waybills", AuditLog.action == AuditAction.DELETE
        )
    )
    assert logged is not None and logged.old_values is not None
    assert logged.old_values["number"] == "FP-2026-09-001"
