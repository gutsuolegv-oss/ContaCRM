from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog, UserRole
from tests.integration.conftest import AuthHeaders

URL = "/api/settings/organization"


async def test_everyone_reads_only_admin_writes(
    api: AsyncClient, auth: AuthHeaders, session: AsyncSession
) -> None:
    admin_user, admin = await auth(UserRole.ADMIN)
    director_user, director = await auth(UserRole.DIRECTOR)
    contabil_user, contabil = await auth(UserRole.CONTABIL)
    # make_user poate crea câte o organizație; aici toți sunt în biroul adminului
    for u in (director_user, contabil_user):
        u.organization_id = admin_user.organization_id
    await session.flush()

    assert (await api.get(URL, headers=contabil)).json()["name"] == "Birou"
    body = {"name": "Conta Expert SRL"}
    assert (await api.patch(URL, json=body, headers=director)).status_code == 403
    assert (await api.patch(URL, json=body, headers=contabil)).status_code == 403

    resp = await api.patch(
        URL,
        json={
            "name": "Conta Expert SRL",
            "idno": "1012600012345",
            "iban": "md24 ag00 0000 0225 1234 5678",
            "email": "Office@Conta.MD",
            "director_name": "Maria Lungu",
        },
        headers=admin,
    )
    assert resp.status_code == 200, resp.text
    org = resp.json()
    assert (org["iban"], org["email"]) == ("MD24AG000000022512345678", "office@conta.md")
    assert (await api.get(URL, headers=contabil)).json()["name"] == "Conta Expert SRL"

    # golirea unui câmp opțional; denumirea nu se poate goli
    cleared = await api.patch(URL, json={"director_name": None}, headers=admin)
    assert cleared.json()["director_name"] is None
    assert (await api.patch(URL, json={"name": None}, headers=admin)).status_code == 422
    bad = await api.patch(URL, json={"idno": "123", "iban": "RO49"}, headers=admin)
    assert bad.status_code == 422


async def test_changes_are_audited(
    api: AsyncClient, auth: AuthHeaders, session: AsyncSession
) -> None:
    _, admin = await auth(UserRole.ADMIN)
    await api.patch(URL, json={"phone": "+373 22 123 456"}, headers=admin)
    log = await session.scalar(select(AuditLog).where(AuditLog.entity_type == "organizations"))
    assert log is not None and log.new_values == {"phone": "+373 22 123 456"}
