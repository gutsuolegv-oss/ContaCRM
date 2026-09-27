"""/api/onec — integrarea cu 1C.

- POST /balances: scriptul de pe calculatorul cu 1C trimite soldurile (cheie în
  `Authorization: Bearer 1c_…`, generată în Setări → 1C). Nu e nevoie de utilizator.
- Restul: doar admin și director (contabilii nu văd datoriile clienților); cheia o
  generează doar adminul.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import CurrentUser, SessionDep
from app.schemas.onec import (
    ApiKeyOut,
    BalancesIn,
    ClientBalanceOut,
    DebtsOut,
    OneCStatusOut,
    SyncResultOut,
)
from app.services.onec import OneCService, ingest

router = APIRouter(prefix="/api/onec", tags=["1C"])

SCRIPT = Path(__file__).resolve().parent.parent / "onec" / "export-balances.ps1"


@router.post("/balances", response_model=SyncResultOut)
async def receive_balances(
    body: BalancesIn,
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> SyncResultOut:
    key = (authorization or "").removeprefix("Bearer ").strip()
    result = await ingest(session, key, body) if key else None
    if result is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Cheie 1C invalidă")
    return result


@router.get("/status", response_model=OneCStatusOut)
async def onec_status(session: SessionDep, user: CurrentUser) -> OneCStatusOut:
    return await OneCService(session, user).status()


@router.post("/api-key", response_model=ApiKeyOut)
async def regenerate_key(session: SessionDep, user: CurrentUser) -> ApiKeyOut:
    """Doar admin. Cheia nouă se arată o singură dată; cea veche nu mai e acceptată."""
    return await OneCService(session, user).regenerate_key()


@router.get("/debts", response_model=DebtsOut)
async def debts(session: SessionDep, user: CurrentUser) -> DebtsOut:
    """Clienții cu datorii la ultima sincronizare și contragenții din 1C negăsiți în CRM."""
    return await OneCService(session, user).debts()


@router.get("/clients/{client_id}/balance", response_model=ClientBalanceOut | None)
async def client_balance(
    client_id: int, session: SessionDep, user: CurrentUser
) -> ClientBalanceOut | None:
    return await OneCService(session, user).client_balance(client_id)


@router.get("/script")
async def download_script(session: SessionDep, user: CurrentUser) -> FileResponse:
    """Scriptul PowerShell pentru calculatorul cu 1C."""
    OneCService(session, user)  # doar admin și director
    return FileResponse(SCRIPT, filename="export-balances.ps1", media_type="text/plain")
