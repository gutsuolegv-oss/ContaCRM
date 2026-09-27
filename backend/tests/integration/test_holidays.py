from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DeadlineRule, Holiday, PeriodType, ReportPeriod
from app.repositories.holiday import HolidayRepository
from app.services.deadlines import calculate_deadline
from app.services.periods import period_bounds


class Spec:
    deadline_rule = DeadlineRule.DAY_OF_NEXT_PERIOD
    deadline_day = 25
    deadline_month = None
    deadline_month_offset = 1


async def test_calendar_from_db(session: AsyncSession) -> None:
    session.add_all(
        [
            Holiday(holiday_date=date(2026, 12, 25), name="Crăciunul"),
            Holiday(holiday_date=date(2026, 7, 25), name="Sâmbătă lucrătoare", is_working=True),
            Holiday(holiday_date=date(2025, 12, 25), name="în afara intervalului"),
        ]
    )
    await session.flush()
    cal = await HolidayRepository(session).load_calendar(date(2026, 1, 1), date(2026, 12, 1))
    # 25 decembrie e după `end`, dar intră în marja de o lună
    assert cal.holidays == frozenset({date(2026, 12, 25)})
    assert cal.working_days == frozenset({date(2026, 7, 25)})

    start, end = period_bounds(PeriodType.LUNAR, 2026, 11)
    nov = ReportPeriod(
        period_type=PeriodType.LUNAR, year=2026, period_no=11, start_date=start, end_date=end
    )
    assert calculate_deadline(Spec(), nov, cal) == date(2026, 12, 28)


async def test_holiday_date_unique(session: AsyncSession) -> None:
    session.add(Holiday(holiday_date=date(2026, 5, 1), name="Ziua Muncii"))
    await session.flush()
    session.add(Holiday(holiday_date=date(2026, 5, 1), name="Dublură"))
    with pytest.raises(IntegrityError):
        await session.flush()
