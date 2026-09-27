"""Schemele API pentru setările biroului (/api/settings)."""

import re
from typing import Annotated

from pydantic import Field, field_validator

from app.schemas.clients import Iban, Idno, Optional255, Optional500, VatCode, normalize_iban
from app.schemas.common import InputModel, Name100, Name255, ORMModel
from app.schemas.users import Email


class OrganizationUpdate(InputModel):
    """Doar câmpurile trimise se modifică; `null` golește un câmp opțional."""

    name: Name255 | None = None
    full_name: Optional500 | None = None
    idno: Idno | None = None
    vat_code: VatCode | None = None
    legal_address: Optional500 | None = None
    phone: Annotated[str, Field(max_length=32)] | None = None
    email: Email | None = None
    website: Optional255 | None = None
    director_name: Optional255 | None = None
    bank_name: Name100 | None = None
    iban: Iban | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, v: str | None) -> str | None:
        if v is None:
            return None
        iban = normalize_iban(v)
        if not re.fullmatch(r"MD[0-9]{2}[A-Z0-9]{20}", iban):
            raise ValueError("IBAN invalid: MD + 2 cifre + 20 caractere")
        return iban


class OrganizationOut(ORMModel):
    id: int
    name: str
    full_name: str | None
    idno: str | None
    vat_code: str | None
    legal_address: str | None
    phone: str | None
    email: str | None
    website: str | None
    director_name: str | None
    bank_name: str | None
    iban: str | None
