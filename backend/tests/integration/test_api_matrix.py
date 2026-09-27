import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, ClientReportType, UserRole
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import Classifier, assign, make_classifier, make_client

API = "/api/classifiers"
AS_OF = {"as_of": "2026-09-01"}


@pytest.fixture
async def classifier(session: AsyncSession) -> Classifier:
    return await make_classifier(session)


@pytest.fixture
async def firm(session: AsyncSession) -> Client:
    return await make_client(session, is_vat_payer=True, has_employees=True)


@pytest.fixture
async def admin(auth: AuthHeaders) -> dict[str, str]:
    return (await auth(UserRole.ADMIN))[1]


def codes(items: list[dict[str, str]]) -> list[str]:
    return sorted(i["code"] for i in items)


async def obligation_count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(ClientReportType)) or 0


async def test_recalculate_preview_then_apply(
    client: AsyncClient,
    session: AsyncSession,
    admin: dict[str, str],
    firm: Client,
    classifier: Classifier,
) -> None:
    preview = await client.post(f"{API}/clients/{firm.id}/recalculate", params=AS_OF, headers=admin)
    assert preview.status_code == 200, preview.text
    assert codes(preview.json()["to_add"]) == ["EXTRASE", "IPC21", "TVA12"]
    assert preview.json()["as_of"] == "2026-09-01"
    assert await obligation_count(session) == 0

    applied = await client.post(
        f"{API}/clients/{firm.id}/recalculate/apply", params=AS_OF, headers=admin
    )
    assert applied.status_code == 200
    assert codes(applied.json()["to_add"]) == ["EXTRASE", "IPC21", "TVA12"]

    listed = (await client.get(f"{API}/clients/{firm.id}/report-types", headers=admin)).json()
    assert sorted(o["report_type"]["code"] for o in listed) == ["EXTRASE", "IPC21", "TVA12"]
    assert {o["source"] for o in listed} == {"auto"}
    assert {o["valid_from"] for o in listed} == {"2026-09-01"}


async def test_manual_assign_and_deactivate(
    client: AsyncClient, admin: dict[str, str], firm: Client, classifier: Classifier
) -> None:
    resp = await client.post(
        f"{API}/clients/{firm.id}/report-types",
        json={"report_type_id": classifier.id("TL13"), "notes": "are taxe locale"},
        headers=admin,
    )
    assert resp.status_code == 201, resp.text
    assert (resp.json()["source"], resp.json()["report_type"]["code"]) == ("manual", "TL13")

    dup = await client.post(
        f"{API}/clients/{firm.id}/report-types",
        json={"report_type_id": classifier.id("TL13")},
        headers=admin,
    )
    assert dup.status_code == 409
    unknown = await client.post(
        f"{API}/clients/{firm.id}/report-types", json={"report_type_id": 999999}, headers=admin
    )
    assert unknown.status_code == 422

    await client.post(f"{API}/clients/{firm.id}/recalculate/apply", params=AS_OF, headers=admin)
    extrase = next(
        o
        for o in (await client.get(f"{API}/clients/{firm.id}/report-types", headers=admin)).json()
        if o["report_type"]["code"] == "EXTRASE"
    )
    off = await client.delete(f"{API}/client-report-types/{extrase['id']}", headers=admin)
    assert off.status_code == 200
    assert (off.json()["is_active"], off.json()["source"]) == (False, "manual")

    diff = (
        await client.post(f"{API}/clients/{firm.id}/recalculate", params=AS_OF, headers=admin)
    ).json()
    assert codes(diff["manual"]) == ["TL13"]
    assert codes(diff["manual_excluded"]) == ["EXTRASE"]
    assert diff["to_add"] == []

    active = await client.get(
        f"{API}/clients/{firm.id}/report-types", params={"active": True}, headers=admin
    )
    assert sorted(o["report_type"]["code"] for o in active.json()) == ["IPC21", "TL13", "TVA12"]


async def test_contabil_sees_only_assigned_clients(
    client: AsyncClient,
    session: AsyncSession,
    auth: AuthHeaders,
    firm: Client,
    classifier: Classifier,
) -> None:
    ana, ana_headers = await auth(UserRole.CONTABIL)
    _, ion_headers = await auth(UserRole.CONTABIL)
    await assign(session, firm, ana)

    url = f"{API}/clients/{firm.id}/report-types"
    assert (await client.get(url, headers=ana_headers)).status_code == 200
    assert (await client.get(url, headers=ion_headers)).status_code == 404
    # contabilul nu scrie, nici pe clienții lui
    write = await client.post(
        url, json={"report_type_id": classifier.id("TL13")}, headers=ana_headers
    )
    assert write.status_code == 403
    for path in ("recalculate", "recalculate/apply"):
        resp = await client.post(f"{API}/clients/{firm.id}/{path}", headers=ana_headers)
        assert resp.status_code == 403


async def test_director_can_write(
    client: AsyncClient, auth: AuthHeaders, firm: Client, classifier: Classifier
) -> None:
    _, director = await auth(UserRole.DIRECTOR)
    resp = await client.post(
        f"{API}/clients/{firm.id}/recalculate/apply", params=AS_OF, headers=director
    )
    assert resp.status_code == 200


async def test_unknown_client_and_obligation(
    client: AsyncClient, admin: dict[str, str], classifier: Classifier
) -> None:
    assert (
        await client.get(f"{API}/clients/999999/report-types", headers=admin)
    ).status_code == 404
    assert (
        await client.post(f"{API}/clients/999999/recalculate", headers=admin)
    ).status_code == 404
    assert (
        await client.delete(f"{API}/client-report-types/999999", headers=admin)
    ).status_code == 404
