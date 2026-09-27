"""Schemele API pentru integrarea cu 1C (soldurile clienților)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, PlainSerializer

from app.schemas.common import InputModel, ORMModel

Amount = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2)]
Money = Annotated[Decimal, PlainSerializer(float, return_type=float)]


# --- ce trimite scriptul din 1C ---


class BalanceRowIn(InputModel):
    idno: Annotated[str, Field(max_length=40)]  # codul fiscal din 1C (curățat în serviciu)
    name: Annotated[str, Field(max_length=500)]
    debit: Amount  # cât datorează biroului
    credit: Amount = Decimal(0)  # avans


class BalancesIn(InputModel):
    as_of: date
    base: Annotated[str, Field(max_length=255)] | None = None
    script_version: Annotated[str, Field(max_length=32)] | None = None
    rows: Annotated[list[BalanceRowIn], Field(max_length=20000)]


class SyncResultOut(InputModel):
    run_id: int
    rows: int
    matched: int
    unmatched: int
    total_debit: Money


# --- ce văd adminul și directorul ---


class RunOut(ORMModel):
    id: int
    received_at: datetime
    as_of: date
    base_name: str | None
    rows: int
    matched: int
    total_debit: Money


class UnmatchedOut(InputModel):
    idno: str
    name: str
    debit: Money
    credit: Money


class OneCStatusOut(InputModel):
    key_configured: bool
    key_hint: str | None
    last_run: RunOut | None


class ApiKeyOut(InputModel):
    key: str  # se arată o singură dată
    status: OneCStatusOut


class DebtRowOut(InputModel):
    client_id: int
    name: str
    idno: str
    debit: Money
    credit: Money
    accountants: list[str]


class DebtsOut(InputModel):
    run: RunOut | None  # ultima sincronizare
    clients: list[DebtRowOut]  # cu sold debitor, cei mai mari primii
    unmatched: list[UnmatchedOut]


class ClientBalanceOut(InputModel):
    as_of: date
    received_at: datetime
    debit: Money
    credit: Money
