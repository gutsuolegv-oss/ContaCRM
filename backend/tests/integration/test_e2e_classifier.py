"""Scenarii complete prin API, pe datele din seed, cu login real.

Clienții și atributele lor se modifică direct în bază: API-ul de clienți nu există încă.
"""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AuditAction, AuditLog, Client, User, UserRole
from app.seed.classifier import seed_classifier
from tests.integration.factories import assign, make_client, make_user

API = "/api/classifiers"
PASSWORD = "parola-e2e-123456"  # noqa: S105
SEPT = {"as_of": "2026-09-01"}
OCT = {"as_of": "2026-10-01"}
PRIMARY_DOCS = ["EXTRASE", "FACT_LIVR", "FACT_PROC"]


@pytest.fixture(autouse=True)
async def seeded(session: AsyncSession) -> None:
    await seed_classifier(session)


async def login(
    client: AsyncClient, session: AsyncSession, role: UserRole
) -> tuple[User, dict[str, str]]:
    user = await make_user(
        session, f"{role.value}@birou.md", role, password_hash=hash_password(PASSWORD)
    )
    resp = await client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return user, {"Authorization": f"Bearer {resp.json()['access_token']}"}


def codes(items: list[dict[str, Any]]) -> list[str]:
    return sorted(i["code"] for i in items)


async def report_type_id(client: AsyncClient, headers: dict[str, str], code: str) -> int:
    types = (await client.get(f"{API}/report-types", headers=headers)).json()
    found: int = next(t["id"] for t in types if t["code"] == code)
    return found


async def active_obligations(
    client: AsyncClient, headers: dict[str, str], firm: Client
) -> list[str]:
    resp = await client.get(
        f"{API}/clients/{firm.id}/report-types", params={"active": True}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return sorted(o["report_type"]["code"] for o in resp.json())


async def test_admin_full_flow(client: AsyncClient, session: AsyncSession) -> None:
    admin, headers = await login(client, session, UserRole.ADMIN)
    firm = await make_client(
        session,
        "1015600034567",
        name="TechSoft Solutions SRL",
        is_vat_payer=True,
        has_employees=True,
        is_it_park_resident=True,
    )

    # 1. Catalogul din seed
    types = (await client.get(f"{API}/report-types", headers=headers)).json()
    assert len(types) == 9
    iu17 = await client.get(
        f"{API}/report-types/{await report_type_id(client, headers, 'IU17')}", headers=headers
    )
    assert [s["code"] for s in iu17.json()["steps"]] == ["transmitere", "inregistrare_1c"]

    # 2. Prima recalculare: previzualizare, apoi aplicare
    preview = (
        await client.post(f"{API}/clients/{firm.id}/recalculate", params=SEPT, headers=headers)
    ).json()
    expected = sorted(["IPC21", "ITPARK_COT", "IU17", "TVA12", *PRIMARY_DOCS])
    assert codes(preview["to_add"]) == expected
    assert await active_obligations(client, headers, firm) == []
    await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=SEPT, headers=headers)
    assert await active_obligations(client, headers, firm) == expected

    # 3. Atribuire manuală: TL13 (fără reguli)
    tl13 = await client.post(
        f"{API}/clients/{firm.id}/report-types",
        json={"report_type_id": await report_type_id(client, headers, "TL13")},
        headers=headers,
    )
    assert tl13.status_code == 201

    # 4. Clientul nu mai are angajați → IPC21 exclus; TL13 manual rămâne
    firm.has_employees = False
    await session.flush()
    diff = (
        await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=OCT, headers=headers)
    ).json()
    assert codes(diff["to_deactivate"]) == ["IPC21"]
    assert codes(diff["manual"]) == ["TL13"]
    assert "IPC21" not in await active_obligations(client, headers, firm)
    assert "TL13" in await active_obligations(client, headers, firm)

    # 5. Regulă nouă pentru POLMED25 (până acum doar manual) → previzualizare → recalculare
    firm.has_transport = True
    await session.flush()
    polmed = await report_type_id(client, headers, "POLMED25")
    rule = await client.post(
        f"{API}/report-types/{polmed}/rules",
        json={
            "name": "Are transport",
            "action": "assign",
            "conditions": {"all": [{"field": "has_transport", "op": "eq", "value": True}]},
        },
        headers=headers,
    )
    assert rule.status_code == 201, rule.text
    who = (
        await client.post(f"{API}/report-types/{polmed}/preview", params=OCT, headers=headers)
    ).json()
    assert [c["id"] for c in who] == [firm.id]
    diff = (
        await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=OCT, headers=headers)
    ).json()
    assert codes(diff["to_add"]) == ["POLMED25"]

    # 6. TVA12 retras la 30.09 → la recalcularea din octombrie dispare
    tva = await report_type_id(client, headers, "TVA12")
    retired = await client.post(
        f"{API}/report-types/{tva}/retire", json={"valid_to": "2026-09-30"}, headers=headers
    )
    assert retired.status_code == 200
    diff = (
        await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=OCT, headers=headers)
    ).json()
    assert codes(diff["to_deactivate"]) == ["TVA12"]
    assert await active_obligations(client, headers, firm) == sorted(
        ["ITPARK_COT", "IU17", "POLMED25", "TL13", *PRIMARY_DOCS]
    )

    # 7. Audit: fiecare pas al adminului e înregistrat, cu el ca autor
    rows = (
        await session.scalars(
            select(AuditLog).where(AuditLog.user_id == admin.id).order_by(AuditLog.id)
        )
    ).all()
    by_entity = [(r.entity_type, r.action) for r in rows]
    assert by_entity.count(("client_report_types", AuditAction.CREATE)) == len(expected) + 2
    assert ("report_rules", AuditAction.CREATE) in by_entity
    assert ("report_types", AuditAction.RETIRE) in by_entity
    retire = next(r for r in rows if r.action is AuditAction.RETIRE)
    assert retire.old_values == {"valid_to": None, "is_active": True}
    assert retire.new_values == {"valid_to": "2026-09-30", "is_active": False}


async def test_contabil_flow(client: AsyncClient, session: AsyncSession) -> None:
    _, admin = await login(client, session, UserRole.ADMIN)
    ana, ana_headers = await login(client, session, UserRole.CONTABIL)
    mine = await make_client(session, "1003600012345", is_vat_payer=True)
    other = await make_client(session, "1002600054321")
    await assign(session, mine, ana)
    for firm in (mine, other):
        await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=SEPT, headers=admin)

    # vede catalogul și obligațiile clientului său
    assert len((await client.get(f"{API}/report-types", headers=ana_headers)).json()) == 9
    assert await active_obligations(client, ana_headers, mine) == sorted(["TVA12", *PRIMARY_DOCS])
    # nu vede alt client și nu poate modifica nimic
    other_resp = await client.get(f"{API}/clients/{other.id}/report-types", headers=ana_headers)
    assert other_resp.status_code == 404
    tva = await report_type_id(client, ana_headers, "TVA12")
    for method, url, body in [
        ("PATCH", f"{API}/report-types/{tva}", {"deadline_day": 20}),
        ("POST", f"{API}/report-types/{tva}/retire", {"valid_to": "2026-12-31"}),
        ("POST", f"{API}/report-types/{tva}/preview", None),
        ("POST", f"{API}/clients/{mine.id}/recalculate/apply", None),
    ]:
        resp = await client.request(method, url, json=body, headers=ana_headers)
        assert resp.status_code == 403, url


async def test_director_edits_deadline(client: AsyncClient, session: AsyncSession) -> None:
    director, headers = await login(client, session, UserRole.DIRECTOR)
    tl13 = await report_type_id(client, headers, "TL13")
    resp = await client.patch(
        f"{API}/report-types/{tl13}",
        json={"deadline_day": 25, "deadline_month_offset": 2},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["deadline_month_offset"] == 2

    row = (
        await session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "report_types", AuditLog.user_id == director.id
            )
        )
    ).one()
    # doar câmpul schimbat efectiv (deadline_day era deja 25)
    assert row.old_values == {"deadline_month_offset": 1}
    assert row.new_values == {"deadline_month_offset": 2}


async def test_session_refresh_mid_flow(client: AsyncClient, session: AsyncSession) -> None:
    user = await make_user(
        session, "admin@birou.md", UserRole.ADMIN, password_hash=hash_password(PASSWORD)
    )
    await client.post("/api/auth/login", json={"email": user.email, "password": PASSWORD})
    # browserul trimite singur cookie-ul primit la login
    refreshed = await client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    headers = {"Authorization": f"Bearer {refreshed.json()['access_token']}"}
    resp = await client.post(
        f"{API}/categories", json={"code": "altele", "name": "Altele"}, headers=headers
    )
    assert resp.status_code == 201
