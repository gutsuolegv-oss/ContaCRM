"""Un client nou, de la introducere la prima lună lucrată, doar prin API (login real).
Singura scriere directă în bază: utilizatorii (API-ul de utilizatori nu există încă)."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AuditLog, Status, StatusSet, UserRole
from app.seed.classifier import seed_classifier
from tests.integration.factories import make_user

PASSWORD = "parola-e2e-123456"  # noqa: S105


async def login(api: AsyncClient, username: str) -> dict[str, str]:
    resp = await api.post("/api/auth/login", json={"username": username, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def codes(items: list[dict[str, Any]]) -> list[str]:
    return sorted(i["code"] for i in items)


async def test_new_client_to_first_month(api: AsyncClient, session: AsyncSession) -> None:
    await seed_classifier(session)
    pw = hash_password(PASSWORD)
    await make_user(session, "director", UserRole.DIRECTOR, password_hash=pw)
    ana = await make_user(session, "ana", UserRole.CONTABIL, password_hash=pw)
    director, ana_h = await login(api, "director"), await login(api, "ana")

    # 1. Ana introduce clientul: i se repartizează ei, obligațiile se calculează de azi
    created = await api.post(
        "/api/clients",
        json={
            "name": "TechSoft Solutions SRL",
            "idno": "1015600034567",
            "legal_form": "SRL",
            "is_it_park_resident": True,
            "locality": "Chișinău",
        },
        headers=ana_h,
    )
    assert created.status_code == 201, created.text
    client_id = created.json()["client"]["id"]
    assert codes(created.json()["recalculation"]["to_add"]) == [
        "EXTRASE", "FACT_LIVR", "FACT_PROC", "ITPARK_COT", "IU17",
    ]  # fmt: skip

    # 2. Completează cartela; află că firma are angajați → IPC21 apare automat
    await api.post(
        f"/api/clients/{client_id}/bank-accounts",
        json={"bank_name": "MAIB", "iban": "MD24 AG00 0000 0225 1234 5678", "is_primary": True},
        headers=ana_h,
    )
    patched = await api.patch(
        f"/api/clients/{client_id}", json={"has_employees": True}, headers=ana_h
    )
    assert codes(patched.json()["recalculation"]["to_add"]) == ["IPC21"]

    # 3. Directorul activează clientul
    activated = await api.patch(
        f"/api/clients/{client_id}", json={"client_status": "active"}, headers=director
    )
    assert activated.json()["client"]["client_status"] == "active"

    # 4. Grila lunii următoare (octombrie: obligațiile încep pe 27.09, deci intră)
    gen = await api.post("/api/grid/generate", params={"year": 2026, "month": 10}, headers=director)
    assert gen.json()["created"] == 6
    grid = (await api.get("/api/grid", params={"year": 2026, "month": 10}, headers=ana_h)).json()
    (row,) = grid["rows"]
    by_code = {rt["id"]: rt["code"] for rt in grid["report_types"]}
    cells = {by_code[e["report_type_id"]]: e for e in row["entries"]}
    assert cells["ITPARK_COT"]["deadline"] == "2026-11-20"  # vineri
    assert cells["IU17"]["deadline"] == "2026-11-25"  # miercuri
    assert {e["assigned_user_id"] for e in row["entries"]} == {ana.id}

    # 5. Ana marchează plata cotizației IT Park
    achitat = await session.scalar(
        select(Status.id).join(StatusSet).where(StatusSet.code == "plata", Status.code == "achitat")
    )
    cot = cells["ITPARK_COT"]
    paid = await api.put(
        f"/api/grid/entries/{cot['id']}/steps/{cot['steps'][0]['step_id']}",
        json={"status_id": achitat},
        headers=ana_h,
    )
    assert paid.json()["is_completed"] is True

    # 6. Auditul are tot drumul clientului, cu autorii corecți
    rows = (await session.scalars(select(AuditLog).order_by(AuditLog.id))).all()
    trail = {(r.entity_type, r.action.value, r.user_id) for r in rows}
    assert ("clients", "create", ana.id) in trail
    assert ("client_assignments", "create", ana.id) in trail
    assert ("client_bank_accounts", "create", ana.id) in trail
    assert ("report_entries", "update", ana.id) in trail
    status_change = next(
        r
        for r in rows
        if r.entity_type == "clients"
        and r.new_values
        and r.new_values.get("client_status") == "active"
    )
    assert status_change.old_values == {"client_status": "onboarding"}
