"""Calculul termenului de depunere.

1. Data de bază, după `deadline_rule` al tipului de raport:
   - day_of_next_period: ziua `deadline_day` din luna aflată la `deadline_month_offset` luni
     după luna în care se termină perioada. Iunie 2026, ziua 25, offset 1 → 25 iulie 2026.
   - fixed_date: prima dată `deadline_day`.`deadline_month` de după sfârșitul perioadei.
   - manual: fără termen calculat (None).
   Dacă luna nu are ziua cerută (31 într-o lună de 30 de zile, 29 februarie într-un an
   nebisect), se ia ultima zi a lunii.
2. Dacă data de bază cade sâmbătă, duminică sau într-o sărbătoare, termenul se mută pe prima
   zi lucrătoare următoare. Iunie 2026: 25 iulie e sâmbătă → termenul e luni, 27 iulie.

Funcția e pură: sărbătorile vin ca parametru (WorkCalendar), citite din tabela holidays de
HolidayRepository.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Protocol

from app.models import DeadlineRule
from app.services.periods import add_months, last_day

SATURDAY = 5


@dataclass(frozen=True)
class WorkCalendar:
    holidays: frozenset[date] = field(default_factory=frozenset)
    # zile de weekend lucrate (ex. sâmbătă lucrătoare în contul unei zile de punte)
    working_days: frozenset[date] = field(default_factory=frozenset)

    def is_working_day(self, day: date) -> bool:
        if day in self.working_days:
            return True
        return day.weekday() < SATURDAY and day not in self.holidays

    def next_working_day(self, day: date) -> date:
        """Ziua însăși, dacă e lucrătoare; altfel prima zi lucrătoare de după."""
        while not self.is_working_day(day):
            day += timedelta(days=1)
        return day


class DeadlineSpec(Protocol):
    @property
    def deadline_rule(self) -> DeadlineRule: ...
    @property
    def deadline_day(self) -> int | None: ...
    @property
    def deadline_month(self) -> int | None: ...
    @property
    def deadline_month_offset(self) -> int: ...


class PeriodLike(Protocol):
    @property
    def end_date(self) -> date: ...


def _clamped(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, last_day(year, month)))


def base_deadline(report_type: DeadlineSpec, period: PeriodLike) -> date | None:
    """Termenul înainte de mutarea pe zi lucrătoare."""
    end = period.end_date
    rule = report_type.deadline_rule
    day = report_type.deadline_day
    if rule is DeadlineRule.MANUAL or day is None:
        return None
    if rule is DeadlineRule.DAY_OF_NEXT_PERIOD:
        year, month = add_months(end.year, end.month, report_type.deadline_month_offset)
        return _clamped(year, month, day)
    fixed_month = report_type.deadline_month
    if fixed_month is None:
        return None
    candidate = _clamped(end.year, fixed_month, day)
    return candidate if candidate > end else _clamped(end.year + 1, fixed_month, day)


def calculate_deadline(
    report_type: DeadlineSpec, period: PeriodLike, work_calendar: WorkCalendar
) -> date | None:
    base = base_deadline(report_type, period)
    return None if base is None else work_calendar.next_working_day(base)
