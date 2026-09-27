"""Schemele API pentru parcul auto: automobile, odometru lunar, foi de parcurs."""

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, PlainSerializer

from app.db.base import RecordStatus
from app.models import FuelType, ReadingSource
from app.schemas.clients import Optional255
from app.schemas.common import InputModel, Name100, ORMModel


def _plate(value: str) -> str:
    """„cdk  540” → „CDK 540”: majuscule, spații simple."""
    plate = re.sub(r"\s+", " ", value.strip().upper())
    if not re.fullmatch(r"[A-Z0-9 -]{2,15}", plate):
        raise ValueError("număr de înmatriculare invalid (litere latine, cifre, spații, -)")
    return plate


Plate = Annotated[str, AfterValidator(_plate)]
FuelNorm = Annotated[Decimal, Field(gt=0, max_digits=5, decimal_places=2)]
Odometer = Annotated[int, Field(ge=0, le=9_999_999)]
Month = Annotated[int, Field(ge=1, le=12)]
# Zecimalele (norma, litrii) pleacă în JSON ca numere, nu ca text.
DecimalNumber = Annotated[Decimal, PlainSerializer(float, return_type=float)]


# --- Automobile ---


class VehicleCreate(InputModel):
    plate: Plate
    model: Name100
    fuel_type: FuelType
    fuel_norm: FuelNorm
    driver: Optional255 | None = None
    initial_odometer: Odometer


class VehicleUpdate(InputModel):
    """`initial_odometer` se poate schimba doar cât automobilul nu are citiri."""

    plate: Plate | None = None
    model: Name100 | None = None
    fuel_type: FuelType | None = None
    fuel_norm: FuelNorm | None = None
    driver: Optional255 | None = None
    initial_odometer: Odometer | None = None


class VehicleOut(ORMModel):
    id: int
    client_id: int
    plate: str
    model: str
    fuel_type: FuelType
    fuel_norm: DecimalNumber
    driver: str | None
    initial_odometer: int
    status: RecordStatus


# --- Odometru ---


class ReadingIn(InputModel):
    end_odometer: Odometer
    source: ReadingSource = ReadingSource.OTHER
    received_on: date


class ReadingOut(ORMModel):
    id: int
    end_odometer: int
    source: ReadingSource
    received_on: date


# --- Foi de parcurs ---


class WaybillBrief(ORMModel):
    id: int
    number: str


class WaybillOut(InputModel):
    id: int
    number: str
    year: int
    month: int
    client_id: int
    client_name: str
    client_idno: str
    vehicle_id: int
    plate: str
    model: str
    fuel_type: FuelType
    driver: str | None
    fuel_norm: DecimalNumber
    start_odometer: int
    end_odometer: int
    km: int
    fuel_liters: DecimalNumber
    issued_at: datetime
    issued_by_name: str | None


# --- Luna ---

FleetStatus = Literal["waiting", "late", "received", "issued"]


class FleetRowOut(InputModel):
    """Un automobil într-o lună. `status`: așteptăm date / întârziat (luna s-a încheiat fără
    date) / date primite / foaie emisă."""

    vehicle: VehicleOut
    start_odometer: int
    reading: ReadingOut | None
    km: int | None
    fuel_liters: DecimalNumber | None
    waybill: WaybillBrief | None
    status: FleetStatus


class FleetMonthOut(InputModel):
    year: int
    month: int
    deadline: date  # ultima zi a lunii
    rows: list[FleetRowOut]
