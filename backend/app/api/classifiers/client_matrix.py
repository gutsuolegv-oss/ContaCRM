"""Obligațiile clienților (matricea) și recalcularea după reguli.

Citirea: admin și director — orice client; contabilul — doar clienții repartizați lui
(pentru ceilalți răspunsul e 404, ca pentru un client inexistent).
Scrierea și recalcularea: admin și director.
"""

from collections.abc import Sequence
from datetime import date

from fastapi import APIRouter, status

from app.api.deps import ClassifierEditor, CurrentUser, SessionDep
from app.core.clock import local_today
from app.models import ClientReportType
from app.schemas.matrix import ClientReportTypeCreate, ClientReportTypeOut, RecalculateDiff
from app.services.access import get_visible_client
from app.services.matrix import MatrixService

router = APIRouter(tags=["clasificator: obligațiile clienților"])


@router.get("/clients/{client_id}/report-types", response_model=list[ClientReportTypeOut])
async def list_client_report_types(
    client_id: int, session: SessionDep, user: CurrentUser, active: bool | None = None
) -> Sequence[ClientReportType]:
    client = await get_visible_client(session, user, client_id)
    rows = await MatrixService(session, user).list_obligations(client)
    return rows if active is None else [r for r in rows if r.is_active is active]


@router.post(
    "/clients/{client_id}/report-types",
    response_model=ClientReportTypeOut,
    status_code=status.HTTP_201_CREATED,
)
async def assign_report_type(
    client_id: int, body: ClientReportTypeCreate, session: SessionDep, user: ClassifierEditor
) -> ClientReportType:
    """Atribuire manuală. Recalcularea n-o va atinge."""
    client = await get_visible_client(session, user, client_id)
    return await MatrixService(session, user).assign_manual(client, body, local_today())


@router.delete("/client-report-types/{obligation_id}", response_model=ClientReportTypeOut)
async def deactivate_report_type(
    obligation_id: int, session: SessionDep, user: ClassifierEditor
) -> ClientReportType:
    """Dezactivare. Obligația devine `manual`, ca recalcularea să n-o readauge."""
    service = MatrixService(session, user)
    row = await service.get_obligation(obligation_id)
    await get_visible_client(session, user, row.client_id)
    return await service.deactivate(row, local_today())


@router.post("/clients/{client_id}/recalculate", response_model=RecalculateDiff)
async def recalculate_preview(
    client_id: int, session: SessionDep, user: ClassifierEditor, as_of: date | None = None
) -> RecalculateDiff:
    """Ce ar schimba recalcularea după regulile actuale. Nu scrie nimic."""
    client = await get_visible_client(session, user, client_id)
    plan = await MatrixService(session, user).plan(client, as_of or local_today())
    return plan.to_diff()


@router.post("/clients/{client_id}/recalculate/apply", response_model=RecalculateDiff)
async def recalculate_apply(
    client_id: int, session: SessionDep, user: ClassifierEditor, as_of: date | None = None
) -> RecalculateDiff:
    """Recalculează și aplică. Diferențele se calculează din nou la aplicare."""
    client = await get_visible_client(session, user, client_id)
    plan = await MatrixService(session, user).apply(client, as_of or local_today())
    return plan.to_diff()
