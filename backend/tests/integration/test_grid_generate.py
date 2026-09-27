from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import RecordStatus
from app.models import (
    AuditLog,
    Client,
    ClientReportType,
    ObligationSource,
    PeriodType,
    ReportEntry,
    ReportEntryStep,
    ReportType,
    Status,
    User,
    UserRole,
)
from app.seed.classifier import seed_classifier
from app.services.errors import ValidationFailedError
from app.services.grid import GridService
from app.services.matrix import MatrixService
from tests.integration.factories import assign, make_client, make_user

JAN_1 = date(2026, 1, 1)


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    await seed_classifier(session)
    return await make_user(session, "admin@birou.md", UserRole.ADMIN)


@pytest.fixture
def grid(session: AsyncSession, admin: User) -> GridService:
    return GridService(session, admin)


async def firm_with_obligations(
    session: AsyncSession,
    admin: User,
    idno: str = "1003600012345",
    as_of: date = JAN_1,
    **kw: object,
) -> Client:
    """Client cu obligațiile calculate de reguli, valabile din `as_of`."""
    client = await make_client(session, idno, **kw)
    await MatrixService(session, admin).apply(client, as_of)
    return client


async def entries(session: AsyncSession, client: Client) -> dict[str, ReportEntry]:
    stmt = (
        select(ReportEntry)
        .where(ReportEntry.client_id == client.id)
        .options(
            selectinload(ReportEntry.report_type),
            selectinload(ReportEntry.steps).selectinload(ReportEntryStep.status),
        )
        .execution_options(populate_existing=True)
    )
    return {e.report_type.code: e for e in (await session.scalars(stmt)).all()}


async def test_generate_september(session: AsyncSession, admin: User, grid: GridService) -> None:
    ana = await make_user(session, "ana@birou.md", UserRole.CONTABIL)
    firm = await firm_with_obligations(session, admin, is_vat_payer=True, has_employees=True)
    await assign(session, firm, ana)

    result = await grid.generate(2026, 9)
    assert [(p.period.period_type, p.period.period_no) for p in result.periods] == [
        (PeriodType.LUNAR, 9),
        (PeriodType.TRIMESTRIAL, 3),
    ]
    assert result.created == 5

    cells = await entries(session, firm)
    assert sorted(cells) == ["EXTRASE", "FACT_LIVR", "FACT_PROC", "IPC21", "TVA12"]
    # 25 octombrie 2026 e duminică → luni 26
    assert cells["TVA12"].deadline == date(2026, 10, 26)
    assert cells["EXTRASE"].deadline is None  # termen manual
    assert {c.assigned_user_id for c in cells.values()} == {ana.id}
    assert not any(c.is_completed for c in cells.values())
    assert [s.status.code for s in cells["TVA12"].steps] == ["neinceput"]
    assert [s.status.code for s in cells["EXTRASE"].steps] == ["neefectuat"]


async def test_generate_is_idempotent(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    await firm_with_obligations(session, admin, is_vat_payer=True)
    first = await grid.generate(2026, 9)
    second = await grid.generate(2026, 9)
    assert (first.created, second.created) == (4, 0)
    assert second.periods[0].existing == 4
    audited = await session.scalar(
        select(func.count()).where(AuditLog.entity_type == "report_entries")
    )
    assert audited == 4


async def test_new_client_added_on_regenerate(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    await firm_with_obligations(session, admin)
    await grid.generate(2026, 9)
    await firm_with_obligations(session, admin, "1000000000002")
    assert (await grid.generate(2026, 9)).created == 3


async def test_semester_in_june(session: AsyncSession, admin: User, grid: GridService) -> None:
    firm = await firm_with_obligations(session, admin)
    tl13 = (await session.scalars(select(ReportType).filter_by(code="TL13"))).one()
    session.add(
        ClientReportType(
            client_id=firm.id,
            report_type_id=tl13.id,
            source=ObligationSource.MANUAL,
            valid_from=JAN_1,
        )
    )
    await session.flush()
    result = await grid.generate(2026, 6)
    assert [p.period.period_type for p in result.periods] == [
        PeriodType.LUNAR,
        PeriodType.TRIMESTRIAL,
        PeriodType.SEMESTRIAL,
    ]
    cells = await entries(session, firm)
    assert cells["TL13"].deadline == date(2026, 7, 27)  # 25 iulie e sâmbătă
    assert [s.status.code for s in cells["TL13"].steps] == ["neinceput", "neefectuat"]


async def test_obligation_ended_later_still_counts(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    firm = await firm_with_obligations(session, admin, has_employees=True)
    firm.has_employees = False
    await MatrixService(session, admin).apply(firm, date(2026, 10, 1))  # IPC21 dezactivat 1.10
    await grid.generate(2026, 9)
    assert "IPC21" in await entries(session, firm)


async def test_obligation_starting_after_period_is_reported(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    # prima recalculare făcută abia în octombrie → obligațiile nu există în septembrie
    firm = await firm_with_obligations(session, admin, as_of=date(2026, 10, 5))
    result = await grid.generate(2026, 9)
    assert result.created == 0
    assert len(result.periods[0].starting_later) == 3
    assert {c for c, _ in result.periods[0].starting_later} == {firm.id}


async def test_closed_period_and_archived_client(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    await firm_with_obligations(session, admin)
    gone = await firm_with_obligations(session, admin, "1000000000002")
    gone.status, gone.deleted_at = RecordStatus.ARCHIVED, datetime.now(UTC)
    await session.flush()

    periods = await grid.ensure_periods(2026, 8)
    periods[0].is_closed = True
    await session.flush()
    closed = await grid.generate(2026, 8)
    assert closed.periods[0].closed and closed.created == 0

    result = await grid.generate(2026, 9)
    assert result.created == 3  # doar clientul activ


async def test_status_set_without_initial(
    session: AsyncSession, admin: User, grid: GridService
) -> None:
    await firm_with_obligations(session, admin)
    for status in (await session.scalars(select(Status).filter_by(is_initial=True))).all():
        status.is_initial = False
    await session.flush()
    with pytest.raises(ValidationFailedError, match="status inițial"):
        await grid.generate(2026, 9)
