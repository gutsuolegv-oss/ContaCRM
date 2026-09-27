from dataclasses import dataclass
from datetime import date

import pytest

from app.models import DeadlineRule, PeriodType
from app.services.deadlines import WorkCalendar, base_deadline, calculate_deadline
from app.services.periods import add_months, period_bounds, periods_ending_in

# Sărbători 2026 folosite în teste (subset).
CALENDAR = WorkCalendar(
    holidays=frozenset(
        {
            date(2026, 5, 1),
            date(2026, 5, 9),
            date(2026, 8, 27),
            date(2026, 8, 31),
            date(2026, 12, 25),
        }
    )
)


@dataclass
class Spec:
    deadline_rule: DeadlineRule = DeadlineRule.DAY_OF_NEXT_PERIOD
    deadline_day: int | None = 25
    deadline_month: int | None = None
    deadline_month_offset: int = 1


@dataclass
class Period:
    end_date: date


def month(year: int, no: int) -> Period:
    return Period(period_bounds(PeriodType.LUNAR, year, no)[1])


# --- Cazurile cerute: zi lucrătoare, sâmbătă, duminică, sărbătoare ---


def test_working_day_unchanged() -> None:
    # mai 2026 → 25 iunie 2026, joi
    assert calculate_deadline(Spec(), month(2026, 5), CALENDAR) == date(2026, 6, 25)


def test_saturday_moves_to_monday() -> None:
    # iunie 2026 → 25 iulie e sâmbătă → luni 27 iulie (exemplul real)
    assert calculate_deadline(Spec(), month(2026, 6), CALENDAR) == date(2026, 7, 27)


def test_sunday_moves_to_monday() -> None:
    # septembrie 2026 → 25 octombrie e duminică → luni 26 octombrie
    assert calculate_deadline(Spec(), month(2026, 9), CALENDAR) == date(2026, 10, 26)


def test_holiday_then_weekend() -> None:
    # noiembrie 2026 → 25 decembrie (Crăciun, vineri), apoi sâmbătă și duminică → 28 decembrie
    assert calculate_deadline(Spec(), month(2026, 11), CALENDAR) == date(2026, 12, 28)


def test_holiday_on_weekday() -> None:
    # iulie 2026, ziua 27 → 27 august (Ziua Independenței, joi) → vineri 28 august
    spec = Spec(deadline_day=27)
    assert calculate_deadline(spec, month(2026, 7), CALENDAR) == date(2026, 8, 28)


def test_consecutive_holidays() -> None:
    # 27 august (joi) și 28 august marcat nelucrător: vineri → sâmbătă → duminică → luni 31
    # august e tot sărbătoare (Limba noastră) → marți 1 septembrie
    cal = WorkCalendar(holidays=CALENDAR.holidays | {date(2026, 8, 28)})
    spec = Spec(deadline_day=27)
    assert calculate_deadline(spec, month(2026, 7), cal) == date(2026, 9, 1)


def test_recovered_working_saturday() -> None:
    # sâmbăta 25 iulie 2026 declarată zi lucrătoare → termenul rămâne 25 iulie
    cal = WorkCalendar(working_days=frozenset({date(2026, 7, 25)}))
    assert calculate_deadline(Spec(), month(2026, 6), cal) == date(2026, 7, 25)


def test_no_holidays_in_calendar() -> None:
    # fără sărbători în tabelă, 25 decembrie e tratat ca zi obișnuită (vineri)
    assert calculate_deadline(Spec(), month(2026, 11), WorkCalendar()) == date(2026, 12, 25)


# --- Perioade mai lungi, offset, fixed_date, manual ---


def test_semester_offset_1() -> None:
    # TL13, semestrul I 2026 → 25 iulie (sâmbătă) → 27 iulie
    sem1 = Period(period_bounds(PeriodType.SEMESTRIAL, 2026, 1)[1])
    assert base_deadline(Spec(), sem1) == date(2026, 7, 25)
    assert calculate_deadline(Spec(), sem1, CALENDAR) == date(2026, 7, 27)


def test_quarter_offset_1() -> None:
    q1 = Period(period_bounds(PeriodType.TRIMESTRIAL, 2026, 1)[1])
    assert base_deadline(Spec(), q1) == date(2026, 4, 25)


def test_annual_offset_3() -> None:
    # anual 2026, ziua 31, offset 3 → 31 martie 2027 (miercuri)
    year = Period(period_bounds(PeriodType.ANUAL, 2026, 1)[1])
    spec = Spec(deadline_day=31, deadline_month_offset=3)
    assert calculate_deadline(spec, year, CALENDAR) == date(2027, 3, 31)


def test_offset_0_same_month() -> None:
    assert base_deadline(Spec(deadline_month_offset=0), month(2026, 6)) == date(2026, 6, 25)


def test_december_rolls_into_next_year() -> None:
    assert base_deadline(Spec(), month(2026, 12)) == date(2027, 1, 25)


def test_day_31_clamped_to_month_end() -> None:
    # august → ziua 31 în septembrie (30 de zile) → 30 septembrie
    assert base_deadline(Spec(deadline_day=31), month(2026, 8)) == date(2026, 9, 30)


def test_fixed_date_next_occurrence() -> None:
    spec = Spec(deadline_rule=DeadlineRule.FIXED_DATE, deadline_day=31, deadline_month=3)
    # anul 2026 se termină în decembrie → 31 martie 2027
    year = Period(period_bounds(PeriodType.ANUAL, 2026, 1)[1])
    assert base_deadline(spec, year) == date(2027, 3, 31)
    # ianuarie 2026 → încă în același an
    assert base_deadline(spec, month(2026, 1)) == date(2026, 3, 31)
    # martie 2026 se termină chiar pe 31 martie → anul următor
    assert base_deadline(spec, month(2026, 3)) == date(2027, 3, 31)


def test_fixed_date_feb_29_non_leap_year() -> None:
    spec = Spec(deadline_rule=DeadlineRule.FIXED_DATE, deadline_day=29, deadline_month=2)
    assert base_deadline(spec, month(2026, 1)) == date(2026, 2, 28)
    assert base_deadline(spec, month(2028, 1)) == date(2028, 2, 29)


def test_manual_has_no_deadline() -> None:
    spec = Spec(deadline_rule=DeadlineRule.MANUAL, deadline_day=None)
    assert calculate_deadline(spec, month(2026, 6), CALENDAR) is None


# --- Perioade ---


@pytest.mark.parametrize(
    ("period_type", "no", "start", "end"),
    [
        (PeriodType.LUNAR, 2, date(2026, 2, 1), date(2026, 2, 28)),
        (PeriodType.LUNAR, 12, date(2026, 12, 1), date(2026, 12, 31)),
        (PeriodType.TRIMESTRIAL, 2, date(2026, 4, 1), date(2026, 6, 30)),
        (PeriodType.SEMESTRIAL, 2, date(2026, 7, 1), date(2026, 12, 31)),
        (PeriodType.ANUAL, 1, date(2026, 1, 1), date(2026, 12, 31)),
    ],
)
def test_period_bounds(period_type: PeriodType, no: int, start: date, end: date) -> None:
    assert period_bounds(period_type, 2026, no) == (start, end)


@pytest.mark.parametrize(("period_type", "no"), [(PeriodType.LUNAR, 13), (PeriodType.ANUAL, 2)])
def test_period_bounds_invalid(period_type: PeriodType, no: int) -> None:
    with pytest.raises(ValueError, match="nu există"):
        period_bounds(period_type, 2026, no)


def test_add_months() -> None:
    assert add_months(2026, 12, 1) == (2027, 1)
    assert add_months(2026, 1, 0) == (2026, 1)
    assert add_months(2026, 6, 24) == (2028, 6)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        (1, [(PeriodType.LUNAR, 1)]),
        (3, [(PeriodType.LUNAR, 3), (PeriodType.TRIMESTRIAL, 1)]),
        (6, [(PeriodType.LUNAR, 6), (PeriodType.TRIMESTRIAL, 2), (PeriodType.SEMESTRIAL, 1)]),
        (9, [(PeriodType.LUNAR, 9), (PeriodType.TRIMESTRIAL, 3)]),
        (
            12,
            [
                (PeriodType.LUNAR, 12),
                (PeriodType.TRIMESTRIAL, 4),
                (PeriodType.SEMESTRIAL, 2),
                (PeriodType.ANUAL, 1),
            ],
        ),
    ],
)
def test_periods_ending_in(month: int, expected: list[tuple[PeriodType, int]]) -> None:
    assert periods_ending_in(month) == expected
