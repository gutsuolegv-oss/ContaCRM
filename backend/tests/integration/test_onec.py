"""Integrarea cu 1C: cheia scriptului, primirea soldurilor și vederile admin/director."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Client, UserRole
from tests.integration.conftest import AuthHeaders
from tests.integration.factories import assign, make_client

API = "/api/onec"


class World:
    admin: dict[str, str]
    director: dict[str, str]
    ana: dict[str, str]
    agro: Client
    vinaria: Client


@pytest.fixture
async def w(session: AsyncSession, auth: AuthHeaders) -> World:
    world = World()
    _, world.admin = await auth(UserRole.ADMIN)
    _, world.director = await auth(UserRole.DIRECTOR)
    ana_user, world.ana = await auth(UserRole.CONTABIL)
    world.agro = await make_client(session, "1003600012345", name="Agro-Nord SRL")
    world.vinaria = await make_client(session, "1002600054321", name="Vinăria Codru SA")
    await assign(session, world.agro, ana_user)
    return world


def payload(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"as_of": "2026-09-27", "base": "Birou_test", "script_version": "1", "rows": list(rows)}


async def new_key(api: AsyncClient, w: World) -> str:
    resp = await api.post(f"{API}/api-key", headers=w.admin)
    assert resp.status_code == 200, resp.text
    key: str = resp.json()["key"]
    return key


async def test_only_admin_and_director(api: AsyncClient, w: World) -> None:
    for url in ("/status", "/debts", f"/clients/{w.agro.id}/balance", "/script"):
        assert (await api.get(f"{API}{url}", headers=w.ana)).status_code == 403, url
        assert (await api.get(f"{API}{url}", headers=w.director)).status_code == 200, url
    assert (await api.post(f"{API}/api-key", headers=w.director)).status_code == 403
    script = await api.get(f"{API}/script", headers=w.admin)
    assert script.content.startswith(b"\xef\xbb\xbf<#")  # UTF-8 cu BOM, pentru PowerShell 5.1


async def test_key_shown_once_and_replaced(api: AsyncClient, w: World) -> None:
    empty = (await api.get(f"{API}/status", headers=w.admin)).json()
    assert (empty["key_configured"], empty["last_run"]) == (False, None)

    key = await new_key(api, w)
    assert key.startswith("1c_")
    status = (await api.get(f"{API}/status", headers=w.admin)).json()
    assert status["key_configured"] and status["key_hint"] == f"…{key[-4:]}"
    assert key not in str(status)

    body = payload()
    assert (await api.post(f"{API}/balances", json=body)).status_code == 401
    wrong = {"Authorization": "Bearer 1c_gresit"}
    assert (await api.post(f"{API}/balances", json=body, headers=wrong)).status_code == 401
    ok = {"Authorization": f"Bearer {key}"}
    assert (await api.post(f"{API}/balances", json=body, headers=ok)).status_code == 200

    await new_key(api, w)  # cheia veche nu mai merge
    assert (await api.post(f"{API}/balances", json=body, headers=ok)).status_code == 401


async def test_balances_matched_by_idno(api: AsyncClient, w: World) -> None:
    headers = {"Authorization": f"Bearer {await new_key(api, w)}"}
    body = payload(
        {"idno": " 1003 6000 12345 ", "name": "AGRO-NORD", "debit": "24800.50", "credit": 0},
        # același IDNO de două ori în 1C (ex. două fișe): se adună
        {"idno": "1003600012345", "name": "Agro-Nord (vechi)", "debit": 199.5, "credit": 10},
        {"idno": "1002600054321", "name": "Vinăria", "debit": 0, "credit": 500},
        {"idno": "", "name": "Persoană fizică", "debit": 1200, "credit": 0},
        {"idno": "9999999999999", "name": "Fără cartelă", "debit": 0, "credit": 0},
    )
    resp = await api.post(f"{API}/balances", json=body, headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "run_id": resp.json()["run_id"],
        "rows": 5,
        "matched": 2,
        "unmatched": 1,  # rândul cu sold zero nu contează
        "total_debit": 25000.0,
    }

    debts = (await api.get(f"{API}/debts", headers=w.director)).json()
    assert debts["run"]["as_of"] == "2026-09-27"
    # doar clienții cu datorie; Vinăria are doar avans
    assert [(c["name"], c["debit"], c["credit"]) for c in debts["clients"]] == [
        ("Agro-Nord SRL", 25000.0, 10.0)
    ]
    assert debts["clients"][0]["accountants"] == ["contabil3"]
    assert [(u["name"], u["debit"]) for u in debts["unmatched"]] == [("Persoană fizică", 1200.0)]

    balance = await api.get(f"{API}/clients/{w.vinaria.id}/balance", headers=w.admin)
    assert (balance.json()["debit"], balance.json()["credit"]) == (0.0, 500.0)

    # o sincronizare nouă înlocuiește starea: Agro a plătit
    await api.post(f"{API}/balances", json=payload(), headers=headers)
    assert (await api.get(f"{API}/debts", headers=w.admin)).json()["clients"] == []
    paid = await api.get(f"{API}/clients/{w.agro.id}/balance", headers=w.admin)
    assert paid.json()["debit"] == 0.0


async def test_validation(api: AsyncClient, w: World) -> None:
    headers = {"Authorization": f"Bearer {await new_key(api, w)}"}
    bad = payload({"idno": "1", "name": "X", "debit": -5, "credit": 0})
    assert (await api.post(f"{API}/balances", json=bad, headers=headers)).status_code == 422
