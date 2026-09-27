from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Holiday
from app.services.deadlines import WorkCalendar

_MARGIN = timedelta(days=31)


class HolidayRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_calendar(self, start: date, end: date) -> WorkCalendar:
        """Calendarul pentru termenele din intervalul [start, end]. Citește și o lună după
        `end`, pentru că un termen de la sfârșitul intervalului se poate muta mai târziu."""
        rows = await self.session.execute(
            select(Holiday.holiday_date, Holiday.is_working).where(
                Holiday.holiday_date.between(start, end + _MARGIN)
            )
        )
        holidays: set[date] = set()
        working: set[date] = set()
        for day, is_working in rows:
            (working if is_working else holidays).add(day)
        return WorkCalendar(frozenset(holidays), frozenset(working))
