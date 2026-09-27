"""Importă toate modelele, ca Alembic și testele să vadă metadata completă."""

import app.models  # noqa: F401
from app.db.base import Base

__all__ = ["Base"]
