from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_today() -> date:
    """Data de azi în fusul orar al biroului (nu UTC: după 21:00 UTC e deja mâine aici)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def local_now() -> datetime:
    """Ora locală a biroului (pentru programări, ex. reamintirea de la 15:00)."""
    return datetime.now(ZoneInfo(get_settings().timezone))


def utc_now() -> datetime:
    return datetime.now(UTC)
