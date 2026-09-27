"""Schemele API pentru utilizatori (/api/users) și schimbarea parolei."""

import re
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, Field, StringConstraints

from app.db.base import RecordStatus
from app.models import UserRole
from app.schemas.common import InputModel, Name255, ORMModel

MIN_PASSWORD_LENGTH = 12


def _username(value: str) -> str:
    """„ Ana.Rusu ” → „ana.rusu”. Se verifică după normalizare (pattern-ul din
    StringConstraints s-ar aplica înaintea ei)."""
    username = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,49}", username):
        raise ValueError(
            "nume de utilizator invalid: 2-50 caractere, litere latine, cifre, punct, _ sau -"
        )
    return username


# Numele de logare, ex. „ana.rusu”.
Username = Annotated[str, AfterValidator(_username)]
# Adresa de email (folosită în alte scheme, ex. setările biroului).
Email = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, to_lower=True, max_length=255, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    ),
]
Password = Annotated[str, Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)]


class UserCreate(InputModel):
    username: Username
    full_name: Name255
    role: UserRole
    password: Password  # inițială; utilizatorul o schimbă la prima logare


class UserUpdate(InputModel):
    username: Username | None = None
    full_name: Name255 | None = None
    role: UserRole | None = None


class PasswordReset(InputModel):
    password: Password


class PasswordChange(InputModel):
    current_password: Annotated[str, Field(max_length=1024)]
    new_password: Password


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    status: RecordStatus
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime
