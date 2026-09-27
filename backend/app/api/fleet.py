"""/api — parcul auto al clienților: automobile, odometrul lunar, foi de parcurs.

Aceleași permisiuni ca la cartela clientului: contabilul doar pe clienții repartizați lui.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.api.deps import CurrentUser, SessionDep, Today
from app.core.clock import local_now, utc_now
from app.models import OdometerReading, Vehicle
from app.schemas.fleet import (
    FleetMonthOut,
    ReadingIn,
    ReadingOut,
    RemindersOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
    WaybillOut,
)
from app.services.fleet import FleetService
from app.services.fleet_reminders import ReminderService

router = APIRouter(tags=["parc auto"])

Year = Annotated[int, Path(ge=2000, le=2100)]
Month = Annotated[int, Path(ge=1, le=12)]


# --- Automobile ---


@router.get("/api/clients/{client_id}/vehicles", response_model=list[VehicleOut])
async def list_vehicles(
    client_id: int, session: SessionDep, user: CurrentUser
) -> Sequence[Vehicle]:
    return await FleetService(session, user).list_vehicles(client_id)


@router.post(
    "/api/clients/{client_id}/vehicles",
    response_model=VehicleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_vehicle(
    client_id: int, body: VehicleCreate, session: SessionDep, user: CurrentUser
) -> Vehicle:
    return await FleetService(session, user).create_vehicle(client_id, body)


@router.patch("/api/vehicles/{vehicle_id}", response_model=VehicleOut)
async def update_vehicle(
    vehicle_id: int, body: VehicleUpdate, session: SessionDep, user: CurrentUser
) -> Vehicle:
    return await FleetService(session, user).update_vehicle(vehicle_id, body)


@router.delete("/api/vehicles/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_vehicle(vehicle_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Scoatere din evidență (ștergere logică); citirile și foile emise rămân."""
    await FleetService(session, user).archive_vehicle(vehicle_id, utc_now())


# --- Luna ---


@router.get("/api/clients/{client_id}/fleet", response_model=FleetMonthOut)
async def fleet_month(
    client_id: int,
    session: SessionDep,
    user: CurrentUser,
    today: Today,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> FleetMonthOut:
    """Automobilele clientului într-o lună: odometru, km, consum, status."""
    return await FleetService(session, user).month(client_id, year, month, today)


@router.put("/api/vehicles/{vehicle_id}/readings/{year}/{month}", response_model=ReadingOut)
async def save_reading(
    vehicle_id: int,
    year: Year,
    month: Month,
    body: ReadingIn,
    session: SessionDep,
    user: CurrentUser,
    today: Today,
) -> OdometerReading:
    """Odometrul la sfârșitul lunii (adăugare sau corectare)."""
    return await FleetService(session, user).save_reading(vehicle_id, year, month, body, today)


@router.delete(
    "/api/vehicles/{vehicle_id}/readings/{year}/{month}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_reading(
    vehicle_id: int, year: Year, month: Month, session: SessionDep, user: CurrentUser
) -> None:
    await FleetService(session, user).delete_reading(vehicle_id, year, month)


# --- Foi de parcurs ---


@router.post(
    "/api/vehicles/{vehicle_id}/readings/{year}/{month}/waybill",
    response_model=WaybillOut,
    status_code=status.HTTP_201_CREATED,
)
async def issue_waybill(
    vehicle_id: int, year: Year, month: Month, session: SessionDep, user: CurrentUser
) -> WaybillOut:
    return await FleetService(session, user).issue_waybill(vehicle_id, year, month)


@router.post(
    "/api/clients/{client_id}/fleet/{year}/{month}/waybills",
    response_model=list[WaybillOut],
    status_code=status.HTTP_201_CREATED,
)
async def issue_month(
    client_id: int, year: Year, month: Month, session: SessionDep, user: CurrentUser
) -> list[WaybillOut]:
    """Foile pentru toate automobilele cu date primite și fără foaie în luna dată."""
    return await FleetService(session, user).issue_month(client_id, year, month)


@router.get("/api/clients/{client_id}/waybills", response_model=list[WaybillOut])
async def list_waybills(client_id: int, session: SessionDep, user: CurrentUser) -> list[WaybillOut]:
    """Foile emise, cele mai recente primele."""
    return await FleetService(session, user).list_waybills(client_id)


@router.get("/api/waybills/{waybill_id}", response_model=WaybillOut)
async def get_waybill(waybill_id: int, session: SessionDep, user: CurrentUser) -> WaybillOut:
    return await FleetService(session, user).get_waybill(waybill_id)


@router.delete("/api/waybills/{waybill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_waybill(waybill_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Anulare: foaia dispare (rămâne în jurnalul de modificări), citirea se poate corecta."""
    await FleetService(session, user).cancel_waybill(waybill_id)


# --- Reamintiri pe Telegram ---


@router.get("/api/clients/{client_id}/fleet/reminders", response_model=RemindersOut)
async def fleet_reminders(
    client_id: int,
    session: SessionDep,
    user: CurrentUser,
    today: Today,
    year: Annotated[int, Query(ge=2000, le=2100)],
    month: Annotated[int, Query(ge=1, le=12)],
) -> RemindersOut:
    """Reamintirile trimise clientului pe lună și dacă se poate trimite una acum."""
    return await ReminderService(session, user).overview(client_id, year, month, today, local_now())


@router.post("/api/clients/{client_id}/fleet/remind", response_model=RemindersOut)
async def remind(
    client_id: int, session: SessionDep, user: CurrentUser, today: Today
) -> RemindersOut:
    """Reamintire manuală pe Telegram, pentru luna în care botul primește acum datele.
    Pleacă în câteva secunde (o trimite procesul botului)."""
    return await ReminderService(session, user).remind(client_id, today, local_now())
