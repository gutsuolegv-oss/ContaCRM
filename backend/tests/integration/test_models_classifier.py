from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Client,
    ClientReportType,
    DeadlineRule,
    LegalForm,
    ObligationSource,
    Periodicity,
    PeriodType,
    ReportCategory,
    ReportEntry,
    ReportPeriod,
    ReportType,
    Status,
    StatusSet,
)


async def _expect_rejected(session: AsyncSession, obj: object) -> None:
    session.add(obj)
    with pytest.raises(DBAPIError):  # IntegrityError e o subclasă
        await session.flush()


@pytest.fixture
async def category(session: AsyncSession) -> ReportCategory:
    c = ReportCategory(code="declaratii_fiscale", name="Declarații fiscale")
    session.add(c)
    await session.flush()
    return c


def _report_type(category: ReportCategory, **kw: object) -> ReportType:
    fields: dict[str, object] = {
        "category_id": category.id,
        "code": "TVA12",
        "name": "Declarația TVA",
        "periodicity": Periodicity.LUNAR,
        "deadline_rule": DeadlineRule.DAY_OF_NEXT_PERIOD,
        "deadline_day": 25,
        "valid_from": date(2026, 1, 1),
    }
    fields.update(kw)
    return ReportType(**fields)


async def test_report_type_defaults(session: AsyncSession, category: ReportCategory) -> None:
    rt = _report_type(category)
    session.add(rt)
    await session.flush()
    await session.refresh(rt)
    assert rt.notify_days_before == [7, 3, 1]
    assert rt.is_active is True
    assert rt.requires_payment is False


async def test_report_type_versions_by_valid_from(
    session: AsyncSession, category: ReportCategory
) -> None:
    session.add(_report_type(category, valid_to=date(2025, 12, 31), valid_from=date(2025, 1, 1)))
    session.add(_report_type(category))
    await session.flush()
    await _expect_rejected(session, _report_type(category))


@pytest.mark.parametrize(
    "kw",
    [
        {"deadline_day": None},  # day_of_next_period fără zi
        {"deadline_rule": DeadlineRule.FIXED_DATE, "deadline_month": None},
        {"deadline_day": 32},
        {"deadline_rule": DeadlineRule.FIXED_DATE, "deadline_month": 13},
        {"valid_to": date(2025, 12, 31)},  # înainte de valid_from
        {"deadline_month_offset": 25},
    ],
)
async def test_report_type_checks(
    session: AsyncSession, category: ReportCategory, kw: dict[str, object]
) -> None:
    await _expect_rejected(session, _report_type(category, **kw))


async def test_manual_deadline_needs_no_day(
    session: AsyncSession, category: ReportCategory
) -> None:
    session.add(
        _report_type(category, code="EXTRASE", deadline_rule=DeadlineRule.MANUAL, deadline_day=None)
    )
    await session.flush()


async def test_one_initial_status_per_set(session: AsyncSession) -> None:
    s = StatusSet(code="depunere", name="Depunere")
    session.add(s)
    await session.flush()
    session.add(Status(status_set_id=s.id, code="neinceput", name="Neînceput", is_initial=True))
    session.add(Status(status_set_id=s.id, code="transmis", name="Transmis"))
    await session.flush()
    await _expect_rejected(
        session, Status(status_set_id=s.id, code="altul", name="Altul", is_initial=True)
    )


@pytest.mark.parametrize(
    ("period_type", "period_no", "ok"),
    [
        (PeriodType.LUNAR, 12, True),
        (PeriodType.LUNAR, 13, False),
        (PeriodType.TRIMESTRIAL, 5, False),
        (PeriodType.SEMESTRIAL, 2, True),
        (PeriodType.SEMESTRIAL, 3, False),
        (PeriodType.ANUAL, 2, False),
    ],
)
async def test_period_no_range(
    session: AsyncSession, period_type: PeriodType, period_no: int, ok: bool
) -> None:
    p = ReportPeriod(
        period_type=period_type,
        year=2026,
        period_no=period_no,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    if ok:
        session.add(p)
        await session.flush()
    else:
        await _expect_rejected(session, p)


async def test_entry_completed_at_matches_flag(
    session: AsyncSession, category: ReportCategory
) -> None:
    client = Client(name="A", idno="1000000000001", legal_form=LegalForm.SRL)
    rt = _report_type(category)
    period = ReportPeriod(
        period_type=PeriodType.LUNAR,
        year=2026,
        period_no=6,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
    )
    session.add_all([client, rt, period])
    await session.flush()
    ids = {"client_id": client.id, "report_type_id": rt.id, "period_id": period.id}
    await _expect_rejected(session, ReportEntry(**ids, is_completed=True))


async def test_client_report_type_unique_per_valid_from(
    session: AsyncSession, category: ReportCategory
) -> None:
    client = Client(name="A", idno="1000000000001", legal_form=LegalForm.SRL)
    rt = _report_type(category)
    session.add_all([client, rt])
    await session.flush()
    row = {"client_id": client.id, "report_type_id": rt.id, "source": ObligationSource.AUTO}
    session.add(ClientReportType(**row))
    await session.flush()
    await _expect_rejected(session, ClientReportType(**row))


async def test_entry_completed_ok(session: AsyncSession, category: ReportCategory) -> None:
    client = Client(name="A", idno="1000000000001", legal_form=LegalForm.SRL)
    rt = _report_type(category)
    period = ReportPeriod(
        period_type=PeriodType.LUNAR,
        year=2026,
        period_no=6,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 30),
    )
    session.add_all([client, rt, period])
    await session.flush()
    session.add(
        ReportEntry(
            client_id=client.id,
            report_type_id=rt.id,
            period_id=period.id,
            deadline=date(2026, 7, 27),
            is_completed=True,
            completed_at=datetime.now(UTC),
        )
    )
    await session.flush()
