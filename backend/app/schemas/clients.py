"""Schemele API pentru clienți (/api/clients), conturi bancare, contacte și repartizări."""

import re
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.db.base import RecordStatus
from app.models import ClientStatus, LegalForm, UserRole
from app.schemas.common import InputModel, Name100, Name255, ORMModel
from app.schemas.matrix import RecalculateDiff

Idno = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{13}$")]
VatCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{7}$")]
Optional255 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
Optional500 = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]


# --- Client ---


class _ClientFields(InputModel):
    full_name: Optional500 | None = None
    is_it_park_resident: bool = False
    has_employees: bool = False
    has_transport: bool = False
    tax_regime: Annotated[str, Field(max_length=30)] | None = None
    locality: Annotated[str, Field(max_length=100)] | None = None
    legal_address: Optional500 | None = None
    caem_code: Annotated[str, Field(max_length=10)] | None = None
    activity: Optional255 | None = None
    registered_on: date | None = None
    client_since: date | None = None
    notes: str | None = None


class ClientCreate(_ClientFields):
    name: Name255
    idno: Idno
    legal_form: LegalForm
    is_vat_payer: bool = False
    vat_code: VatCode | None = None

    @model_validator(mode="after")
    def _vat(self) -> Self:
        if self.vat_code is not None and not self.is_vat_payer:
            raise ValueError("vat_code se completează doar la plătitorii de TVA")
        return self


class ClientUpdate(InputModel):
    """Doar câmpurile trimise se modifică. `client_status`: doar admin și director."""

    name: Name255 | None = None
    full_name: Optional500 | None = None
    idno: Idno | None = None
    legal_form: LegalForm | None = None
    is_vat_payer: bool | None = None
    vat_code: VatCode | None = None
    is_it_park_resident: bool | None = None
    has_employees: bool | None = None
    has_transport: bool | None = None
    tax_regime: Annotated[str, Field(max_length=30)] | None = None
    locality: Annotated[str, Field(max_length=100)] | None = None
    legal_address: Optional500 | None = None
    caem_code: Annotated[str, Field(max_length=10)] | None = None
    activity: Optional255 | None = None
    registered_on: date | None = None
    client_since: date | None = None
    notes: str | None = None
    client_status: ClientStatus | None = None


class UserBrief(ORMModel):
    id: int
    full_name: str
    username: str
    role: UserRole


class BankAccountOut(ORMModel):
    id: int
    bank_name: str
    iban: str
    currency: str
    is_primary: bool


class ContactOut(ORMModel):
    id: int
    full_name: str
    position: str | None
    is_primary: bool
    phone: str | None
    email: str | None


class ClientListItem(ORMModel):
    id: int
    name: str
    idno: str
    legal_form: LegalForm
    is_vat_payer: bool
    locality: str | None
    client_status: ClientStatus
    status: RecordStatus
    accountants: list[UserBrief]


class ClientListOut(ORMModel):
    total: int
    items: list[ClientListItem]


class ClientOut(ORMModel):
    id: int
    name: str
    full_name: str | None
    idno: str
    legal_form: LegalForm
    is_vat_payer: bool
    vat_code: str | None
    is_it_park_resident: bool
    has_employees: bool
    has_transport: bool
    tax_regime: str | None
    locality: str | None
    legal_address: str | None
    caem_code: str | None
    activity: str | None
    registered_on: date | None
    client_since: date | None
    client_status: ClientStatus
    notes: str | None
    status: RecordStatus
    created_at: datetime
    updated_at: datetime
    accountants: list[UserBrief]
    bank_accounts: list[BankAccountOut]
    contacts: list[ContactOut]


class ClientSaveOut(ORMModel):
    """Clientul salvat și, dacă s-au schimbat atributele pentru reguli, ce s-a schimbat în
    obligațiile lui (recalculare automată)."""

    client: ClientOut
    recalculation: RecalculateDiff | None


# --- Conturi bancare ---


def normalize_iban(value: str) -> str:
    """„md24 ag00 0000…” → „MD24AG0000…”."""
    return re.sub(r"\s+", "", value).upper()


Iban = Annotated[str, Field(max_length=40)]  # formatul exact îl verifică validatorul
Currency = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z]{3}$")
]


class BankAccountCreate(InputModel):
    bank_name: Name100
    iban: Iban
    currency: Currency = "MDL"
    is_primary: bool = False

    @field_validator("iban")
    @classmethod
    def _iban(cls, v: str) -> str:
        iban = normalize_iban(v)
        if not re.fullmatch(r"MD[0-9]{2}[A-Z0-9]{20}", iban):
            raise ValueError("IBAN invalid: MD + 2 cifre + 20 caractere")
        return iban


class BankAccountUpdate(InputModel):
    bank_name: Name100 | None = None
    iban: Iban | None = None
    currency: Currency | None = None
    is_primary: bool | None = None

    @field_validator("iban")
    @classmethod
    def _iban(cls, v: str | None) -> str | None:
        return None if v is None else BankAccountCreate._iban(v)


# --- Contacte ---


class ContactCreate(InputModel):
    full_name: Name255
    position: Annotated[str, Field(max_length=100)] | None = None
    is_primary: bool = False
    phone: Annotated[str, Field(max_length=32)] | None = None
    email: Annotated[str, Field(max_length=255)] | None = None


class ContactUpdate(InputModel):
    full_name: Name255 | None = None
    position: Annotated[str, Field(max_length=100)] | None = None
    is_primary: bool | None = None
    phone: Annotated[str, Field(max_length=32)] | None = None
    email: Annotated[str, Field(max_length=255)] | None = None


# --- Repartizări ---


class AssignmentCreate(InputModel):
    user_id: int


class AssignmentOut(ORMModel):
    id: int
    user: UserBrief
    assigned_at: datetime
    assigned_by: int | None
    unassigned_at: datetime | None
    unassigned_by: int | None
