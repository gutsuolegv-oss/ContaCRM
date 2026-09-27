"""/api/grid — grila de execuție pe luna de gestiune.

Citirea și lucrul pe celule (statusuri, notițe): toți utilizatorii; contabilul doar pe clienții
repartizați lui. Generarea, termenul, contabilul responsabil, închiderea lunii: admin și director.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import ClassifierEditor, CurrentUser, SessionDep, Today
from app.core.clock import utc_now
from app.models import ReportPeriod
from app.schemas.grid import (
    EntryOut,
    EntryUpdate,
    GenerationOut,
    GridOut,
    PeriodGenerationOut,
    PeriodOut,
    StepStatusIn,
)
from app.services.grid import GridService, entry_out

router = APIRouter(prefix="/api/grid", tags=["grila de execuție"])

Year = Annotated[int, Query(ge=2000, le=2100)]
Month = Annotated[int, Query(ge=1, le=12)]


@router.get("", response_model=GridOut)
async def view_grid(
    session: SessionDep,
    user: CurrentUser,
    today: Today,
    year: Year,
    month: Month,
    client_id: int | None = None,
    report_type_id: int | None = None,
    assigned_user_id: int | None = None,
    only_open: bool = False,
    only_overdue: bool = False,
) -> GridOut:
    return await GridService(session, user).view(
        year,
        month,
        today,
        client_id=client_id,
        report_type_id=report_type_id,
        assigned_user_id=assigned_user_id,
        only_open=only_open,
        only_overdue=only_overdue,
    )


@router.post("/generate", response_model=GenerationOut)
async def generate(
    session: SessionDep, user: ClassifierEditor, year: Year, month: Month
) -> GenerationOut:
    """Adaugă celulele care lipsesc pentru perioadele care se termină în luna dată."""
    result = await GridService(session, user).generate(year, month)
    return GenerationOut(
        year=result.year,
        month=result.month,
        created=result.created,
        periods=[
            PeriodGenerationOut(
                period=PeriodOut.model_validate(p.period),
                created=p.created,
                existing=p.existing,
                closed=p.closed,
                starting_later=p.starting_later,
            )
            for p in result.periods
        ],
    )


@router.get("/entries/{entry_id}", response_model=EntryOut)
async def get_entry(
    entry_id: int, session: SessionDep, user: CurrentUser, today: Today
) -> EntryOut:
    return entry_out(await GridService(session, user).get_entry(entry_id), today)


@router.patch("/entries/{entry_id}", response_model=EntryOut)
async def update_entry(
    entry_id: int, body: EntryUpdate, session: SessionDep, user: CurrentUser, today: Today
) -> EntryOut:
    """Contabilul: doar `notes`. Admin și director: și `deadline`, `assigned_user_id`."""
    entry = await GridService(session, user).update_entry(entry_id, body)
    return entry_out(entry, today)


@router.put("/entries/{entry_id}/steps/{step_id}", response_model=EntryOut)
async def set_step_status(
    entry_id: int,
    step_id: int,
    body: StepStatusIn,
    session: SessionDep,
    user: CurrentUser,
    today: Today,
) -> EntryOut:
    entry = await GridService(session, user).set_step_status(
        entry_id, step_id, body.status_id, utc_now()
    )
    return entry_out(entry, today)


@router.post("/periods/{period_id}/close", response_model=PeriodOut)
async def close_period(period_id: int, session: SessionDep, user: ClassifierEditor) -> ReportPeriod:
    return await GridService(session, user).set_period_closed(period_id, True)


@router.post("/periods/{period_id}/reopen", response_model=PeriodOut)
async def reopen_period(
    period_id: int, session: SessionDep, user: ClassifierEditor
) -> ReportPeriod:
    return await GridService(session, user).set_period_closed(period_id, False)
