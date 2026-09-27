"""O lună de lucru, cap-coadă prin API, cu login real: obligații → grilă → contabilul
completează → luna se închide."""

from datetime import date

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models import AuditLog, Status, StatusSet, UserRole
from app.seed.classifier import seed_classifier
from tests.integration.factories import assign, make_client, make_user

PASSWORD = "parola-e2e-123456"  # noqa: S105
SEPT = {"year": 2026, "month": 9}


async def login(client: AsyncClient, email: str) -> dict[str, str]:
    resp = await client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def test_month_of_work(client: AsyncClient, session: AsyncSession) -> None:
    await seed_classifier(session)
    pw = hash_password(PASSWORD)
    await make_user(session, "admin@birou.md", UserRole.ADMIN, password_hash=pw)
    ana = await make_user(session, "ana@birou.md", UserRole.CONTABIL, password_hash=pw)
    firm = await make_client(session, name="Agro-Nord SRL", is_vat_payer=True)
    await assign(session, firm, ana)
    admin_h, ana_h = await login(client, "admin@birou.md"), await login(client, "ana@birou.md")
    final = dict(
        (
            await session.execute(
                select(StatusSet.code, Status.id)
                .join(Status, Status.status_set_id == StatusSet.id)
                .where(Status.is_final.is_(True))
            )
        )
        .tuples()
        .all()
    )

    # 1. Adminul calculează obligațiile (din 1 ianuarie) și generează grila lui septembrie
    await client.post(
        f"/api/classifiers/clients/{firm.id}/recalculate/apply",
        params={"as_of": "2026-01-01"},
        headers=admin_h,
    )
    gen = (await client.post("/api/grid/generate", params=SEPT, headers=admin_h)).json()
    assert gen["created"] == 4  # TVA12, FACT_LIVR, FACT_PROC, EXTRASE

    # 2. Ana își vede clientul și bifează toate etapele
    grid = (await client.get("/api/grid", params=SEPT, headers=ana_h)).json()
    (row,) = grid["rows"]
    assert {e["assigned_user_id"] for e in row["entries"]} == {ana.id}
    set_of_step = {"transmitere": "depunere", "efectuare": "binar"}
    for entry in row["entries"]:
        for step in entry["steps"]:
            resp = await client.put(
                f"/api/grid/entries/{entry['id']}/steps/{step['step_id']}",
                json={"status_id": final[set_of_step[step["code"]]]},
                headers=ana_h,
            )
            assert resp.status_code == 200, resp.text
            assert resp.json()["is_completed"] is True

    # 3. Nimic deschis; adminul închide luna; Ana nu mai poate modifica
    still_open = await client.get("/api/grid", params={**SEPT, "only_open": True}, headers=ana_h)
    assert still_open.json()["rows"] == []
    period_id = gen["periods"][0]["period"]["id"]
    await client.post(f"/api/grid/periods/{period_id}/close", headers=admin_h)
    entry_id = row["entries"][0]["id"]
    blocked = await client.patch(
        f"/api/grid/entries/{entry_id}", json={"notes": "târziu"}, headers=ana_h
    )
    assert blocked.status_code == 409

    # 4. Auditul arată cine a completat fiecare raport
    completions = (
        await session.scalars(
            select(AuditLog).where(
                AuditLog.entity_type == "report_entries", AuditLog.action == "update"
            )
        )
    ).all()
    assert len(completions) == 4
    assert {a.user_id for a in completions} == {ana.id}
    assert all(a.new_values and a.new_values["is_completed"] for a in completions)
    assert date.fromisoformat(grid["periods"][0]["end_date"]) == date(2026, 9, 30)
