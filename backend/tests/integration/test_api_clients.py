from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User, UserRole
from app.seed.classifier import seed_classifier
from tests.integration.conftest import AuthHeaders

AGRO: dict[str, Any] = {
    "name": "Agro-Nord SRL",
    "idno": "1003600012345",
    "legal_form": "SRL",
    "is_vat_payer": True,
    "vat_code": "0600012",
    "locality": "Bălți",
}


class People:
    admin: dict[str, str]
    director: dict[str, str]
    ana: dict[str, str]
    ion: dict[str, str]
    ana_user: User
    ion_user: User


@pytest.fixture
async def people(session: AsyncSession, auth: AuthHeaders) -> People:
    await seed_classifier(session)
    p = People()
    _, p.admin = await auth(UserRole.ADMIN)
    _, p.director = await auth(UserRole.DIRECTOR)
    p.ana_user, p.ana = await auth(UserRole.CONTABIL)
    p.ion_user, p.ion = await auth(UserRole.CONTABIL)
    return p


async def create(api: AsyncClient, headers: dict[str, str], **kw: Any) -> dict[str, Any]:
    resp = await api.post("/api/clients", json={**AGRO, **kw}, headers=headers)
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


def codes(items: list[dict[str, Any]]) -> list[str]:
    return sorted(i["code"] for i in items)


async def test_accountant_onboards_client(api: AsyncClient, people: People) -> None:
    body = await create(api, people.ana)
    client = body["client"]
    assert client["client_status"] == "onboarding"
    assert [a["id"] for a in client["accountants"]] == [people.ana_user.id]
    assert codes(body["recalculation"]["to_add"]) == ["EXTRASE", "FACT_LIVR", "FACT_PROC", "TVA12"]
    assert body["recalculation"]["as_of"] == "2026-09-27"

    # obligațiile se văd și în matricea clientului
    obligations = await api.get(
        f"/api/classifiers/clients/{client['id']}/report-types", headers=people.ana
    )
    assert len(obligations.json()) == 4

    # activarea: doar admin / director
    activate = {"client_status": "active"}
    denied = await api.patch(f"/api/clients/{client['id']}", json=activate, headers=people.ana)
    assert denied.status_code == 403
    ok = await api.patch(f"/api/clients/{client['id']}", json=activate, headers=people.director)
    assert ok.json()["client"]["client_status"] == "active"
    assert ok.json()["recalculation"] is None


async def test_rule_attribute_change(api: AsyncClient, people: People) -> None:
    client = (await create(api, people.ana))["client"]
    resp = await api.patch(
        f"/api/clients/{client['id']}",
        json={"has_employees": True, "is_vat_payer": False},
        headers=people.ana,
    )
    assert resp.status_code == 200, resp.text
    diff = resp.json()["recalculation"]
    assert codes(diff["to_add"]) == ["IPC21"]
    assert codes(diff["to_deactivate"]) == ["TVA12"]
    assert resp.json()["client"]["vat_code"] is None


async def test_visibility_and_search(api: AsyncClient, people: People) -> None:
    mine = (await create(api, people.ana))["client"]
    other = (
        await create(
            api,
            people.admin,
            name="Vinăria Codru SA",
            idno="1002600054321",
            is_vat_payer=False,
            vat_code=None,
        )
    )["client"]

    ana_list = (await api.get("/api/clients", headers=people.ana)).json()
    assert (ana_list["total"], [c["id"] for c in ana_list["items"]]) == (1, [mine["id"]])
    assert (await api.get(f"/api/clients/{other['id']}", headers=people.ion)).status_code == 404
    assert (await api.get(f"/api/clients/{mine['id']}", headers=people.ion)).status_code == 404

    admin_list = await api.get("/api/clients", params={"q": "codru"}, headers=people.admin)
    assert [c["name"] for c in admin_list.json()["items"]] == ["Vinăria Codru SA"]
    by_vat = await api.get("/api/clients", params={"is_vat_payer": True}, headers=people.admin)
    assert by_vat.json()["total"] == 1
    bad = await api.get("/api/clients", params={"limit": 1000}, headers=people.admin)
    assert bad.status_code == 422


async def test_duplicate_idno_and_validation(api: AsyncClient, people: People) -> None:
    await create(api, people.admin)
    dup = await api.post("/api/clients", json=AGRO, headers=people.admin)
    assert dup.status_code == 409
    bad = await api.post(
        "/api/clients", json={**AGRO, "idno": "123", "vat_code": None}, headers=people.admin
    )
    assert bad.status_code == 422
    no_vat = await api.post(
        "/api/clients",
        json={**AGRO, "idno": "1000000000009", "is_vat_payer": False},
        headers=people.admin,
    )
    assert no_vat.status_code == 422  # vat_code fără TVA


async def test_archive(api: AsyncClient, people: People) -> None:
    client = (await create(api, people.ana))["client"]
    url = f"/api/clients/{client['id']}"
    assert (await api.delete(url, headers=people.ana)).status_code == 403
    assert (await api.delete(url, headers=people.admin)).status_code == 204
    assert (await api.get(url, headers=people.ana)).status_code == 404
    archived = await api.get(url, headers=people.admin)
    assert archived.json()["status"] == "archived"
    listed = await api.get("/api/clients", params={"include_archived": True}, headers=people.admin)
    assert listed.json()["total"] == 1
    # același IDNO poate fi folosit din nou
    await create(api, people.admin)


async def test_bank_accounts_and_contacts(api: AsyncClient, people: People) -> None:
    client = (await create(api, people.ana))["client"]
    base = f"/api/clients/{client['id']}"
    card = await api.post(
        f"{base}/bank-accounts",
        json={"bank_name": "MAIB", "iban": "md24 ag00 0000 0225 1234 5678", "is_primary": True},
        headers=people.ana,
    )
    assert card.status_code == 201, card.text
    (maib,) = card.json()["bank_accounts"]
    assert maib["iban"] == "MD24AG000000022512345678"

    card = await api.post(
        f"{base}/bank-accounts",
        json={
            "bank_name": "Victoriabank",
            "iban": "MD68VI000000022512345679",
            "currency": "EUR",
            "is_primary": True,
        },
        headers=people.ana,
    )
    primary = [a["bank_name"] for a in card.json()["bank_accounts"] if a["is_primary"]]
    assert primary == ["Victoriabank"]
    bad = await api.post(
        f"{base}/bank-accounts", json={"bank_name": "X", "iban": "RO49AAAA"}, headers=people.ana
    )
    assert bad.status_code == 422

    card = await api.delete(f"/api/bank-accounts/{maib['id']}", headers=people.ana)
    assert [a["bank_name"] for a in card.json()["bank_accounts"]] == ["Victoriabank"]

    card = await api.post(
        f"{base}/contacts",
        json={"full_name": "Petru Moraru", "position": "Administrator", "is_primary": True},
        headers=people.ana,
    )
    contact_id = card.json()["contacts"][0]["id"]
    card = await api.patch(
        f"/api/contacts/{contact_id}", json={"phone": "+373 69 123 456"}, headers=people.ana
    )
    assert card.json()["contacts"][0]["phone"] == "+373 69 123 456"
    denied = await api.patch(f"/api/contacts/{contact_id}", json={"phone": "x"}, headers=people.ion)
    assert denied.status_code == 404


async def test_assignments(api: AsyncClient, people: People) -> None:
    client = (await create(api, people.ana))["client"]
    url = f"/api/clients/{client['id']}/assignments"
    body = {"user_id": people.ion_user.id}
    assert (await api.post(url, json=body, headers=people.ana)).status_code == 403
    history = await api.post(url, json=body, headers=people.admin)
    assert history.status_code == 201
    assert {a["user"]["id"] for a in history.json()} == {people.ana_user.id, people.ion_user.id}
    assert (await api.post(url, json=body, headers=people.admin)).status_code == 409

    ion_sees = await api.get(f"/api/clients/{client['id']}", headers=people.ion)
    assert ion_sees.status_code == 200

    ana_row = next(a for a in history.json() if a["user"]["id"] == people.ana_user.id)
    closed = await api.delete(f"/api/client-assignments/{ana_row['id']}", headers=people.admin)
    assert next(a for a in closed.json() if a["id"] == ana_row["id"])["unassigned_at"]
    assert (await api.get(f"/api/clients/{client['id']}", headers=people.ana)).status_code == 404
    assert len((await api.get(url, headers=people.ion)).json()) == 2


async def test_anonymous_rejected(api: AsyncClient) -> None:
    assert (await api.get("/api/clients")).status_code == 401
