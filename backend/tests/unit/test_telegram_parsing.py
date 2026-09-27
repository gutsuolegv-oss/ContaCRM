from datetime import date

import pytest

from app.services.telegram import parse_odometer, reading_month


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("123906", 123906),
        (" 123 906 ", 123906),
        ("123.906 km", 123906),
        ("123,906", 123906),
        ("123\u00a0906", 123906),
        ("1 234 567", 1234567),
        ("50000KM", 50000),
        ("0", 0),
        ("123,5", None),  # zecimale: nu e un număr de kilometri
        ("12 34", None),  # grupe greșite
        ("aproape 100000", None),
        ("", None),
        ("99999999", None),  # peste 7 cifre
    ],
)
def test_parse_odometer(text: str, expected: int | None) -> None:
    assert parse_odometer(text) == expected


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 10, 3), (2026, 9)),  # începutul lunii: luna trecută
        (date(2026, 10, 10), (2026, 9)),
        (date(2026, 10, 11), (2026, 10)),  # după 10: luna curentă
        (date(2026, 10, 31), (2026, 10)),
        (date(2027, 1, 5), (2026, 12)),  # peste an
    ],
)
def test_reading_month(today: date, expected: tuple[int, int]) -> None:
    assert reading_month(today) == expected
