"""Limitele perioadelor de gestiune."""

import calendar
from datetime import date

from app.models import PeriodType

MONTHS_PER_PERIOD = {
    PeriodType.LUNAR: 1,
    PeriodType.TRIMESTRIAL: 3,
    PeriodType.SEMESTRIAL: 6,
    PeriodType.ANUAL: 12,
}


def add_months(year: int, month: int, months: int) -> tuple[int, int]:
    """(an, lună) mutat cu `months` luni. add_months(2026, 12, 1) → (2027, 1)."""
    index = year * 12 + (month - 1) + months
    return index // 12, index % 12 + 1


def last_day(year: int, month: int) -> int:
    return calendar.monthrange(year, month)[1]


def period_bounds(period_type: PeriodType, year: int, period_no: int) -> tuple[date, date]:
    """Prima și ultima zi a perioadei. period_bounds(SEMESTRIAL, 2026, 1) → (1 ian, 30 iun)."""
    months = MONTHS_PER_PERIOD[period_type]
    if not 1 <= period_no <= 12 // months:
        raise ValueError(f"perioada {period_no} nu există pentru {period_type}")
    first_month = (period_no - 1) * months + 1
    end_year, end_month = add_months(year, first_month, months - 1)
    return date(year, first_month, 1), date(end_year, end_month, last_day(end_year, end_month))
