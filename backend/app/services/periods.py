"""Limitele perioadelor de gestiune."""

import calendar
from datetime import date

from app.models import Periodicity, PeriodType

MONTHS_PER_PERIOD = {
    PeriodType.LUNAR: 1,
    PeriodType.TRIMESTRIAL: 3,
    PeriodType.SEMESTRIAL: 6,
    PeriodType.ANUAL: 12,
}


# Periodicitatea unui raport → tipul perioadei. `la_cerere` nu are perioade fixe.
PERIOD_TYPE_FOR = {
    Periodicity.LUNAR: PeriodType.LUNAR,
    Periodicity.TRIMESTRIAL: PeriodType.TRIMESTRIAL,
    Periodicity.SEMESTRIAL: PeriodType.SEMESTRIAL,
    Periodicity.ANUAL: PeriodType.ANUAL,
}


def periods_ending_in(month: int) -> list[tuple[PeriodType, int]]:
    """Perioadele care se termină în luna dată, ca (tip, număr): grila lunii le conține pe
    toate. Septembrie → lunar 9 și trimestrul III; decembrie → și semestrul II și anul."""
    return [
        (period_type, month // months)
        for period_type, months in MONTHS_PER_PERIOD.items()
        if month % months == 0
    ]


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
