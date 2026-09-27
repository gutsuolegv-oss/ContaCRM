from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Client,
    DeadlineRule,
    Holiday,
    LegalForm,
    PeriodType,
    ReportPeriod,
    ReportRule,
    ReportType,
    Status,
    StatusSet,
)
from app.repositories.holiday import HolidayRepository
from app.seed.classifier import HOLIDAYS_2026, REPORT_TYPES, seed_classifier
from app.services.deadlines import calculate_deadline
from app.services.periods import period_bounds
from app.services.rules_engine import evaluate_client_reports


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_seed_creates_everything_once(session: AsyncSession) -> None:
    first = await seed_classifier(session)
    assert first.created["report_types"] == 9
    assert first.created["report_categories"] == 4
    assert first.created["status_sets"] == 3
    assert first.created["statuses"] == 8
    assert first.created["report_rules"] == 8
    assert first.created["holidays"] == 10
    audited = await _count(session, AuditLog)
    assert audited == sum(first.created.values())

    second = await seed_classifier(session)
    assert sum(second.created.values()) == 0
    assert second.existing == first.created
    assert await _count(session, ReportType) == 9
    assert await _count(session, AuditLog) == audited


async def test_seed_does_not_overwrite_edits(session: AsyncSession) -> None:
    await seed_classifier(session)
    tva = (await session.scalars(select(ReportType).filter_by(code="TVA12"))).one()
    tva.deadline_day = 28
    await session.flush()
    await seed_classifier(session)
    await session.refresh(tva)
    assert tva.deadline_day == 28


async def test_seed_content(session: AsyncSession) -> None:
    await seed_classifier(session)
    types = {rt.code: rt for rt in (await session.scalars(select(ReportType))).all()}
    assert set(types) == {rt.code for rt in REPORT_TYPES}
    assert types["TL13"].periodicity.value == "semestrial"
    assert types["ITPARK_COT"].deadline_day == 20
    assert types["ITPARK_COT"].requires_payment is True
    assert types["EXTRASE"].deadline_rule is DeadlineRule.MANUAL
    assert types["EXTRASE"].deadline_day is None

    # un singur status inițial și unul final în fiecare set
    for status_set in (await session.scalars(select(StatusSet))).all():
        statuses = (
            await session.scalars(select(Status).filter_by(status_set_id=status_set.id))
        ).all()
        assert sum(s.is_initial for s in statuses) == 1
        assert sum(s.is_final for s in statuses) == 1

    rows = await session.execute(
        select(ReportType.code, func.count(ReportRule.id))
        .join(ReportRule, ReportRule.report_type_id == ReportType.id, isouter=True)
        .group_by(ReportType.code)
    )
    rules_per_type: dict[str, int] = {code: count for code, count in rows}
    assert rules_per_type["IPC21"] == 2
    assert rules_per_type["TL13"] == rules_per_type["POLMED25"] == 0


async def test_holidays(session: AsyncSession) -> None:
    await seed_classifier(session)
    days = set((await session.scalars(select(Holiday.holiday_date))).all())
    assert date(2026, 6, 1) in days
    assert date(2026, 1, 2) not in days
    assert len(days) == len(HOLIDAYS_2026)


async def test_seeded_rules_and_deadlines(session: AsyncSession) -> None:
    await seed_classifier(session)
    ids = {rt.code: rt.id for rt in (await session.scalars(select(ReportType))).all()}
    rules = (await session.scalars(select(ReportRule))).all()

    it_firm = Client(
        name="TechSoft SRL",
        idno="1015600034567",
        legal_form=LegalForm.SRL,
        is_vat_payer=True,
        has_employees=True,
        is_it_park_resident=True,
        has_transport=False,
        tax_regime=None,
    )
    expected = {"TVA12", "IPC21", "IU17", "ITPARK_COT", "FACT_LIVR", "FACT_PROC", "EXTRASE"}
    assert set(evaluate_client_reports(it_firm, rules)) == {ids[c] for c in expected}

    # iunie 2026 → 25 iulie e sâmbătă → 27 iulie; noiembrie → 25 decembrie (Crăciun) → 28
    cal = await HolidayRepository(session).load_calendar(date(2026, 1, 1), date(2026, 12, 31))
    tva = await session.get(ReportType, ids["TVA12"])
    assert tva is not None
    for month, expected_deadline in [(6, date(2026, 7, 27)), (11, date(2026, 12, 28))]:
        start, end = period_bounds(PeriodType.LUNAR, 2026, month)
        period = ReportPeriod(
            period_type=PeriodType.LUNAR,
            year=2026,
            period_no=month,
            start_date=start,
            end_date=end,
        )
        assert calculate_deadline(tva, period, cal) == expected_deadline
