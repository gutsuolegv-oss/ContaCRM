from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLog, UserRole
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import eq, make_classifier, make_client

API = "/api/classifiers"

REPORT_TYPE: dict[str, Any] = {
    "code": "IU17",
    "name": "Impozit unic IT Park",
    "periodicity": "lunar",
    "deadline_rule": "day_of_next_period",
    "deadline_day": 25,
    "valid_from": "2026-01-01",
}


@pytest.fixture
async def admin(auth: AuthHeaders) -> dict[str, str]:
    return (await auth(UserRole.ADMIN))[1]


async def _category(client: AsyncClient, headers: dict[str, str]) -> int:
    resp = await client.post(
        f"{API}/categories",
        json={"code": "declaratii_fiscale", "name": "Declarații fiscale", "sort_order": 10},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    cat_id: int = resp.json()["id"]
    return cat_id


# --- Permisiuni ---


@pytest.mark.parametrize(
    ("role", "expected"),
    [(UserRole.ADMIN, 201), (UserRole.DIRECTOR, 201), (UserRole.CONTABIL, 403)],
)
async def test_write_roles(
    client: AsyncClient, auth: AuthHeaders, role: UserRole, expected: int
) -> None:
    _, headers = await auth(role)
    resp = await client.post(
        f"{API}/categories", json={"code": "plati", "name": "Plăți"}, headers=headers
    )
    assert resp.status_code == expected


async def test_contabil_can_read(
    client: AsyncClient, auth: AuthHeaders, admin: dict[str, str]
) -> None:
    await _category(client, admin)
    _, contabil = await auth(UserRole.CONTABIL)
    for path in ("/categories", "/status-sets", "/report-types"):
        resp = await client.get(API + path, headers=contabil)
        assert resp.status_code == 200, path


async def test_anonymous_rejected(client: AsyncClient) -> None:
    assert (await client.get(f"{API}/categories")).status_code == 401


async def test_preview_hidden_from_contabil(
    client: AsyncClient, session: AsyncSession, auth: AuthHeaders
) -> None:
    c = await make_classifier(session)
    _, contabil = await auth(UserRole.CONTABIL)
    resp = await client.post(f"{API}/report-types/{c.id('TVA12')}/preview", headers=contabil)
    assert resp.status_code == 403


# --- Categorii ---


async def test_categories_crud(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    cat_id = await _category(client, admin)
    dup = await client.post(
        f"{API}/categories", json={"code": "declaratii_fiscale", "name": "X"}, headers=admin
    )
    assert dup.status_code == 409
    assert "declaratii_fiscale" in dup.json()["detail"]

    resp = await client.patch(
        f"{API}/categories/{cat_id}", json={"name": "Declarații"}, headers=admin
    )
    assert resp.json()["name"] == "Declarații"
    assert (await client.delete(f"{API}/categories/{cat_id}", headers=admin)).status_code == 204

    active = await client.get(f"{API}/categories", params={"active": True}, headers=admin)
    assert active.json() == []
    everything = await client.get(f"{API}/categories", headers=admin)
    assert everything.json()[0]["is_active"] is False

    actions = (
        await session.scalars(select(AuditLog.action).where(AuditLog.entity_id == cat_id))
    ).all()
    assert actions == [AuditAction.CREATE, AuditAction.UPDATE, AuditAction.DELETE]


async def test_not_found_and_validation(client: AsyncClient, admin: dict[str, str]) -> None:
    resp = await client.patch(f"{API}/categories/999999", json={"name": "X"}, headers=admin)
    assert resp.status_code == 404
    resp = await client.post(
        f"{API}/categories", json={"code": "cu spatiu", "name": "X"}, headers=admin
    )
    assert resp.status_code == 422
    resp = await client.post(
        f"{API}/categories", json={"code": "x", "name": "X", "necunoscut": 1}, headers=admin
    )
    assert resp.status_code == 422


# --- Seturi de statusuri ---


async def test_status_sets(client: AsyncClient, admin: dict[str, str]) -> None:
    resp = await client.post(
        f"{API}/status-sets",
        json={
            "code": "depunere",
            "name": "Depunere",
            "statuses": [
                {"code": "neinceput", "name": "Neînceput", "is_initial": True, "sort_order": 1},
                {"code": "transmis", "name": "Transmis", "sort_order": 2},
            ],
        },
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    assert [s["code"] for s in resp.json()["statuses"]] == ["neinceput", "transmis"]

    resp = await client.post(
        f"{API}/status-sets/{set_id}/statuses",
        json={"code": "incarcat", "name": "Încărcat", "is_final": True, "sort_order": 3},
        headers=admin,
    )
    assert resp.status_code == 201
    status_id = resp.json()["id"]
    second_initial = await client.post(
        f"{API}/status-sets/{set_id}/statuses",
        json={"code": "x", "name": "X", "is_initial": True},
        headers=admin,
    )
    assert second_initial.status_code == 409

    resp = await client.patch(
        f"{API}/statuses/{status_id}", json={"name": "Încărcat în SFS"}, headers=admin
    )
    assert resp.json()["name"] == "Încărcat în SFS"
    assert (await client.delete(f"{API}/statuses/{status_id}", headers=admin)).status_code == 204

    listed = (await client.get(f"{API}/status-sets", headers=admin)).json()
    assert [s["code"] for s in listed[0]["statuses"]] == ["neinceput", "transmis"]

    renamed = await client.patch(
        f"{API}/status-sets/{set_id}", json={"name": "Depunere declarații"}, headers=admin
    )
    assert renamed.json()["name"] == "Depunere declarații"
    assert len(renamed.json()["statuses"]) == 2


# --- Tipuri de rapoarte, etape, reguli ---


async def test_report_type_lifecycle(client: AsyncClient, admin: dict[str, str]) -> None:
    cat_id = await _category(client, admin)
    resp = await client.post(
        f"{API}/report-types", json={**REPORT_TYPE, "category_id": cat_id}, headers=admin
    )
    assert resp.status_code == 201, resp.text
    rt = resp.json()
    assert rt["notify_days_before"] == [7, 3, 1]
    assert rt["deadline_month_offset"] == 1

    bad = await client.patch(
        f"{API}/report-types/{rt['id']}", json={"deadline_rule": "fixed_date"}, headers=admin
    )
    assert bad.status_code == 422
    assert "deadline_month" in bad.json()["detail"]

    retired = await client.post(
        f"{API}/report-types/{rt['id']}/retire", json={"valid_to": "2026-12-31"}, headers=admin
    )
    assert retired.status_code == 200
    assert (retired.json()["is_active"], retired.json()["valid_to"]) == (False, "2026-12-31")

    # nu există ștergere fizică
    assert (await client.delete(f"{API}/report-types/{rt['id']}", headers=admin)).status_code == 405

    # versiune nouă a aceluiași cod
    v2 = await client.post(
        f"{API}/report-types",
        json={**REPORT_TYPE, "category_id": cat_id, "valid_from": "2027-01-01"},
        headers=admin,
    )
    assert v2.status_code == 201
    active = await client.get(f"{API}/report-types", params={"active": True}, headers=admin)
    assert [t["valid_from"] for t in active.json()] == ["2027-01-01"]


async def test_report_type_filters(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    c = await make_classifier(session)
    semestrial = await client.get(
        f"{API}/report-types", params={"periodicity": "semestrial"}, headers=admin
    )
    assert [t["code"] for t in semestrial.json()] == ["TL13"]
    by_cat = await client.get(
        f"{API}/report-types", params={"category_id": c.category.id}, headers=admin
    )
    assert len(by_cat.json()) == 4


async def test_steps_and_rules_in_detail(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    c = await make_classifier(session)
    tl13 = c.id("TL13")
    binar = await client.post(
        f"{API}/status-sets",
        json={
            "code": "binar",
            "name": "Binar",
            "statuses": [
                {"code": "neefectuat", "name": "Neefectuat", "is_initial": True},
                {"code": "efectuat", "name": "Efectuat", "is_final": True},
            ],
        },
        headers=admin,
    )
    set_id = binar.json()["id"]
    step = await client.post(
        f"{API}/report-types/{tl13}/steps",
        json={"status_set_id": set_id, "code": "inregistrare_1c", "name": "Înregistrare 1C"},
        headers=admin,
    )
    assert step.status_code == 201
    rule = await client.post(
        f"{API}/report-types/{tl13}/rules",
        json={"name": "Cu transport", "action": "assign", "conditions": eq("has_transport", True)},
        headers=admin,
    )
    assert rule.status_code == 201, rule.text

    detail = (await client.get(f"{API}/report-types/{tl13}", headers=admin)).json()
    assert [s["code"] for s in detail["steps"]] == ["inregistrare_1c"]
    assert detail["rules"][0]["conditions"] == eq("has_transport", True)

    rules = (await client.get(f"{API}/report-types/{tl13}/rules", headers=admin)).json()
    assert len(rules) == 1
    patched = await client.patch(
        f"{API}/rules/{rule.json()['id']}", json={"priority": 300}, headers=admin
    )
    assert patched.json()["priority"] == 300
    assert (
        await client.delete(f"{API}/rules/{rule.json()['id']}", headers=admin)
    ).status_code == 204
    assert (
        await client.patch(
            f"{API}/steps/{step.json()['id']}", json={"is_required": False}, headers=admin
        )
    ).json()["is_required"] is False
    assert (
        await client.delete(f"{API}/steps/{step.json()['id']}", headers=admin)
    ).status_code == 204


async def test_rule_with_invalid_field_rejected(
    client: AsyncClient, session: AsyncSession, admin: dict[str, str]
) -> None:
    c = await make_classifier(session)
    resp = await client.post(
        f"{API}/report-types/{c.id('TL13')}/rules",
        json={"name": "Greșită", "action": "assign", "conditions": eq("is_vat_payr", True)},
        headers=admin,
    )
    assert resp.status_code == 422
    assert "câmp necunoscut" in resp.text


async def test_preview(client: AsyncClient, session: AsyncSession, admin: dict[str, str]) -> None:
    c = await make_classifier(session)
    vat = await make_client(session, "1000000000001", name="Agro-Nord SRL", is_vat_payer=True)
    await make_client(session, "1000000000002")
    resp = await client.post(
        f"{API}/report-types/{c.id('TVA12')}/preview",
        params={"as_of": "2026-09-01"},
        headers=admin,
    )
    assert resp.status_code == 200
    assert resp.json() == [{"id": vat.id, "name": "Agro-Nord SRL", "idno": "1000000000001"}]
