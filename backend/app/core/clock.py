from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_today() -> date:
    """Data de azi în fusul orar al biroului (nu UTC: după 21:00 UTC e deja mâine aici)."""
    return datetime.now(ZoneInfo(get_settings().timezone)).date()
