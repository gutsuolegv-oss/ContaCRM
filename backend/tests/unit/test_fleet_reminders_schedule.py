from datetime import datetime, time

import pytest

from app.models import ReminderKind
from app.services.fleet_reminders import SendWindow, due_auto

REQ, REM = ReminderKind.AUTO_REQUEST, ReminderKind.AUTO_REMINDER


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 9, 29, 20, 0), []),  # nu e ultima zi
        (datetime(2026, 9, 30, 14, 59), []),  # ultima zi, dar înainte de 15:00
        (datetime(2026, 9, 30, 15, 0), [(REQ, 2026, 9)]),
        (datetime(2026, 10, 1, 9, 0), [(REQ, 2026, 9)]),  # recuperare: botul era oprit
        (datetime(2026, 10, 3, 9, 59), [(REQ, 2026, 9)]),
        (datetime(2026, 10, 3, 10, 0), [(REM, 2026, 9)]),
        (datetime(2026, 10, 10, 23, 0), [(REM, 2026, 9)]),
        (datetime(2026, 10, 11, 10, 0), []),  # după 10: luna trecută nu mai primește date
        (datetime(2027, 1, 4, 12, 0), [(REM, 2026, 12)]),  # peste an
        (datetime(2027, 2, 28, 15, 30), [(REQ, 2027, 2)]),
    ],
)
def test_due_auto(now: datetime, expected: list[tuple[ReminderKind, int, int]]) -> None:
    assert due_auto(now) == expected


WORKWEEK = SendWindow(frozenset({1, 2, 3, 4, 5}), time(9, 0), time(18, 0))


@pytest.mark.parametrize(
    ("now", "open_now", "next_start"),
    [
        (datetime(2026, 9, 28, 10, 0), True, datetime(2026, 9, 28, 10, 0)),  # luni, 10:00
        (datetime(2026, 9, 28, 8, 59), False, datetime(2026, 9, 28, 9, 0)),
        (datetime(2026, 9, 28, 18, 0), False, datetime(2026, 9, 29, 9, 0)),  # 18:00 e închis
        (datetime(2026, 10, 2, 17, 30), True, datetime(2026, 10, 2, 17, 30)),  # vineri
        (datetime(2026, 10, 2, 18, 30), False, datetime(2026, 10, 5, 9, 0)),  # → luni
        (datetime(2026, 10, 3, 12, 0), False, datetime(2026, 10, 5, 9, 0)),  # sâmbătă
    ],
)
def test_send_window(now: datetime, open_now: bool, next_start: datetime) -> None:
    assert WORKWEEK.contains(now) is open_now
    assert WORKWEEK.next_start(now) == next_start


def test_send_window_label() -> None:
    assert WORKWEEK.label() == "L-V, 09:00-18:00"
    assert SendWindow(frozenset({1, 3}), time(8, 30), time(12, 0)).label() == "L, Mi, 08:30-12:00"
