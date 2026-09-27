"""Parcul auto al clienților: automobile, odometrul la sfârșit de lună, foi de parcurs.

Permisiuni: ca la cartela clientului — admin și director pe toți clienții, contabilul doar
pe clienții repartizați lui (pentru ceilalți: 404).

Reguli:
- odometrul de început al unei luni = sfârșitul lunii anterioare cu date (sau odometrul
  inițial al automobilului); sfârșitul nu poate fi mai mic decât începutul și nici mai mare
  decât sfârșitul lunii următoare cu date;
- o citire cu foaie de parcurs emisă nu se mai modifică, și nici cea dinaintea ei (i-ar
  schimba foii începutul); foaia se anulează întâi;
- nu se introduc date pentru luni viitoare.
"""

import calendar
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import Client, OdometerReading, User, Vehicle, Waybill
from app.repositories.fleet import ReadingRepository, VehicleRepository, WaybillRepository
from app.schemas.fleet import (
    FleetMonthOut,
    FleetRowOut,
    FleetStatus,
    FleetSummaryOut,
    FleetVehicleBrief,
    ReadingIn,
    ReadingOut,
    VehicleCreate,
    VehicleOut,
    VehicleUpdate,
    WaybillBrief,
    WaybillOut,
)
from app.services.access import get_visible_client
from app.services.audit import AuditService, snapshot
from app.services.classifier import apply_changes
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)

_PLATE_CONFLICT = "Există deja un automobil în evidență cu acest număr"
_CENT = Decimal("0.01")


def last_day(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def fuel_liters(km: int, norm: Decimal) -> Decimal:
    """Consumul normat: km * normă / 100, rotunjit la 0,01 l."""
    return (Decimal(km) * norm / 100).quantize(_CENT, rounding=ROUND_HALF_UP)


def _key(reading: OdometerReading) -> tuple[int, int]:
    return (reading.year, reading.month)


class _History:
    """Citirile unui automobil, în ordine cronologică."""

    def __init__(self, vehicle: Vehicle, readings: Sequence[OdometerReading]) -> None:
        self.vehicle = vehicle
        self.readings = sorted(readings, key=_key)

    def at(self, period: tuple[int, int]) -> OdometerReading | None:
        return next((r for r in self.readings if _key(r) == period), None)

    def before(self, period: tuple[int, int]) -> OdometerReading | None:
        earlier = [r for r in self.readings if _key(r) < period]
        return earlier[-1] if earlier else None

    def after(self, period: tuple[int, int]) -> OdometerReading | None:
        return next((r for r in self.readings if _key(r) > period), None)

    def start(self, period: tuple[int, int]) -> int:
        prev = self.before(period)
        return prev.end_odometer if prev else self.vehicle.initial_odometer


def _status(reading: OdometerReading | None, deadline: date, today: date) -> FleetStatus:
    """Starea unui automobil pe lună: așteptăm date / întârziat / date primite / foaie emisă."""
    if reading is None:
        return "late" if today > deadline else "waiting"
    return "issued" if reading.waybill else "received"


async def month_summaries(
    session: AsyncSession, client_ids: Sequence[int], year: int, month: int, today: date
) -> dict[int, FleetSummaryOut]:
    """Rezumatul foilor de parcurs pe lună, pentru clienții care au automobile active. Nu
    verifică accesul: apelantul trimite doar clienții pe care utilizatorul îi vede."""
    vehicles = await VehicleRepository(session).list_for_clients(client_ids)
    readings = await ReadingRepository(session).for_vehicles([v.id for v in vehicles])
    by_period = {(r.vehicle_id, r.year, r.month): r for r in readings}
    deadline = last_day(year, month)
    items: dict[int, list[FleetVehicleBrief]] = defaultdict(list)
    for v in vehicles:
        status = _status(by_period.get((v.id, year, month)), deadline, today)
        items[v.client_id].append(FleetVehicleBrief(vehicle_id=v.id, plate=v.plate, status=status))
    result = {}
    for client_id, briefs in items.items():
        count = {s: sum(b.status == s for b in briefs) for s in ("issued", "received", "late")}
        missing = len(briefs) - count["issued"] - count["received"]
        result[client_id] = FleetSummaryOut(
            vehicles=len(briefs),
            issued=count["issued"],
            received=count["received"],
            missing=missing,
            late=count["late"] > 0,
            items=briefs,
        )
    return result


class FleetService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        """`actor` None: botul Telegram, care lucrează doar prin `record_reading`, pe un
        automobil pe care l-a verificat el (al clientului legat de chat)."""
        self.session = session
        self.actor = actor
        self.audit = AuditService(session, actor)
        self.vehicles = VehicleRepository(session)
        self.readings = ReadingRepository(session)
        self.waybills = WaybillRepository(session)

    # --- acces ---

    @property
    def _user(self) -> User:
        if self.actor is None:
            raise ForbiddenError("Acțiune permisă doar unui utilizator")
        return self.actor

    @property
    def _actor_id(self) -> int | None:
        return self.actor.id if self.actor is not None else None

    async def _client(self, client_id: int) -> Client:
        return await get_visible_client(self.session, self._user, client_id)

    async def _vehicle(self, vehicle_id: int) -> Vehicle:
        vehicle = await self.vehicles.get_active(vehicle_id)
        if vehicle is None:
            raise NotFoundError("Automobilul nu există")
        try:
            await self._client(vehicle.client_id)
        except NotFoundError as e:
            raise NotFoundError("Automobilul nu există") from e
        return vehicle

    async def _history(self, vehicle: Vehicle) -> _History:
        return _History(vehicle, await self.readings.for_vehicles([vehicle.id]))

    # --- automobile ---

    async def list_vehicles(self, client_id: int) -> Sequence[Vehicle]:
        client = await self._client(client_id)
        return await self.vehicles.list_for_client(client.id)

    async def create_vehicle(self, client_id: int, data: VehicleCreate) -> Vehicle:
        client = await self._client(client_id)
        async with conflict_guard(self.session, _PLATE_CONFLICT):
            vehicle = Vehicle(client_id=client.id, **data.model_dump())
            self.session.add(vehicle)
        self.audit.created(vehicle)
        await self.session.commit()
        return vehicle

    async def update_vehicle(self, vehicle_id: int, data: VehicleUpdate) -> Vehicle:
        vehicle = await self._vehicle(vehicle_id)
        values = data.model_dump(exclude_unset=True)
        if (
            values.get("initial_odometer", vehicle.initial_odometer) != vehicle.initial_odometer
            and (await self._history(vehicle)).readings
        ):
            raise ValidationFailedError(
                "Odometrul inițial nu se mai schimbă după ce automobilul are citiri"
            )
        before = snapshot(vehicle)
        async with conflict_guard(self.session, _PLATE_CONFLICT):
            apply_changes(vehicle, values)
        self.audit.changed(vehicle, before)
        await self.session.commit()
        return vehicle

    async def archive_vehicle(self, vehicle_id: int, now: datetime) -> None:
        """Scoatere din evidență (ștergere logică). Citirile și foile rămân."""
        vehicle = await self._vehicle(vehicle_id)
        before = snapshot(vehicle)
        async with conflict_guard(self.session, "Automobilul nu a putut fi scos din evidență"):
            vehicle.status = RecordStatus.ARCHIVED
            vehicle.deleted_at = now
            vehicle.deleted_by = self._actor_id
        self.audit.changed(vehicle, before)
        await self.session.commit()

    # --- luna ---

    async def month(self, client_id: int, year: int, month: int, today: date) -> FleetMonthOut:
        client = await self._client(client_id)
        vehicles = await self.vehicles.list_for_client(client.id)
        by_vehicle: dict[int, list[OdometerReading]] = defaultdict(list)
        for r in await self.readings.for_vehicles([v.id for v in vehicles]):
            by_vehicle[r.vehicle_id].append(r)

        period, deadline = (year, month), last_day(year, month)
        rows = []
        for vehicle in vehicles:
            history = _History(vehicle, by_vehicle[vehicle.id])
            start = history.start(period)
            reading = history.at(period)
            km = reading.end_odometer - start if reading else None
            status = _status(reading, deadline, today)
            rows.append(
                FleetRowOut(
                    vehicle=VehicleOut.model_validate(vehicle),
                    start_odometer=start,
                    reading=ReadingOut.model_validate(reading) if reading else None,
                    km=km,
                    fuel_liters=fuel_liters(km, vehicle.fuel_norm) if km is not None else None,
                    waybill=(
                        WaybillBrief.model_validate(reading.waybill)
                        if reading and reading.waybill
                        else None
                    ),
                    status=status,
                )
            )
        return FleetMonthOut(year=year, month=month, deadline=deadline, rows=rows)

    # --- odometru ---

    @staticmethod
    def _check_not_future(year: int, month: int, today: date) -> None:
        if (year, month) > (today.year, today.month):
            raise ValidationFailedError("Nu se introduc date pentru o lună viitoare")

    @staticmethod
    def _check_unlocked(history: _History, period: tuple[int, int]) -> None:
        """Citirea din `period` se poate schimba: nici ea, nici următoarea n-au foaie emisă."""
        current, following = history.at(period), history.after(period)
        if current is not None and current.waybill is not None:
            raise ConflictError(
                f"Foaia de parcurs {current.waybill.number} e emisă; anuleaz-o întâi"
            )
        if following is not None and following.waybill is not None:
            raise ConflictError(
                f"Luna următoare are foaia {following.waybill.number}, care pornește de la "
                "această valoare; anuleaz-o întâi"
            )

    async def save_reading(
        self, vehicle_id: int, year: int, month: int, data: ReadingIn, today: date
    ) -> OdometerReading:
        """Adaugă sau înlocuiește odometrul de sfârșit al lunii."""
        vehicle = await self._vehicle(vehicle_id)
        return await self.record_reading(vehicle, year, month, data, today)

    async def record_reading(
        self, vehicle: Vehicle, year: int, month: int, data: ReadingIn, today: date
    ) -> OdometerReading:
        """Regulile și salvarea citirii, fără verificarea accesului (o face apelantul)."""
        self._check_not_future(year, month, today)
        if data.received_on > today:
            raise ValidationFailedError("Data primirii nu poate fi în viitor")
        history = await self._history(vehicle)
        period = (year, month)
        self._check_unlocked(history, period)

        start = history.start(period)
        if data.end_odometer < start:
            raise ValidationFailedError(
                f"Odometrul de sfârșit ({data.end_odometer}) e mai mic decât cel de început "
                f"({start})"
            )
        following = history.after(period)
        if following is not None and data.end_odometer > following.end_odometer:
            raise ValidationFailedError(
                f"Odometrul depășește valoarea din {following.month:02d}.{following.year} "
                f"({following.end_odometer})"
            )

        reading = history.at(period)
        if reading is None:
            async with conflict_guard(self.session, "Citirea pe această lună există deja"):
                reading = OdometerReading(
                    vehicle_id=vehicle.id,
                    year=year,
                    month=month,
                    entered_by=self._actor_id,
                    **data.model_dump(),
                )
                self.session.add(reading)
            self.audit.created(reading)
        else:
            before = snapshot(reading)
            async with conflict_guard(self.session, "Citirea nu a putut fi salvată"):
                apply_changes(reading, data.model_dump() | {"entered_by": self._actor_id})
            self.audit.changed(reading, before)
        await self.session.commit()
        return reading

    async def delete_reading(self, vehicle_id: int, year: int, month: int) -> None:
        vehicle = await self._vehicle(vehicle_id)
        history = await self._history(vehicle)
        reading = history.at((year, month))
        if reading is None:
            raise NotFoundError("Nu există date pentru această lună")
        self._check_unlocked(history, (year, month))
        before = snapshot(reading)
        async with conflict_guard(self.session, "Citirea nu a putut fi ștearsă"):
            await self.session.delete(reading)
        self.audit.deleted(reading, before)
        await self.session.commit()

    # --- foi de parcurs ---

    async def _next_number(self, year: int, month: int) -> str:
        prefix = f"FP-{year}-{month:02d}-"
        used = [
            int(n.removeprefix(prefix)) for n in await self.waybills.numbers_with_prefix(prefix)
        ]
        return f"{prefix}{max(used, default=0) + 1:03d}"

    async def _issue(self, vehicle: Vehicle, history: _History, reading: OdometerReading) -> int:
        start = history.start(_key(reading))
        async with conflict_guard(
            self.session, "Foaia de parcurs nu a putut fi emisă (reîncearcă)"
        ):
            waybill = Waybill(
                reading_id=reading.id,
                number=await self._next_number(reading.year, reading.month),
                plate=vehicle.plate,
                model=vehicle.model,
                fuel_type=vehicle.fuel_type,
                driver=vehicle.driver,
                fuel_norm=vehicle.fuel_norm,
                start_odometer=start,
                end_odometer=reading.end_odometer,
                fuel_liters=fuel_liters(reading.end_odometer - start, vehicle.fuel_norm),
                issued_by=self._actor_id,
            )
            self.session.add(waybill)
        self.audit.created(waybill)
        return waybill.id

    async def issue_waybill(self, vehicle_id: int, year: int, month: int) -> WaybillOut:
        vehicle = await self._vehicle(vehicle_id)
        history = await self._history(vehicle)
        reading = history.at((year, month))
        if reading is None:
            raise ValidationFailedError("Lipsește odometrul pentru această lună")
        if reading.waybill is not None:
            raise ConflictError(f"Foaia {reading.waybill.number} e deja emisă")
        waybill_id = await self._issue(vehicle, history, reading)
        await self.session.commit()
        return await self.get_waybill(waybill_id)

    async def issue_month(self, client_id: int, year: int, month: int) -> list[WaybillOut]:
        """Foile pentru toate automobilele clientului cu date primite și fără foaie."""
        client = await self._client(client_id)
        vehicles = await self.vehicles.list_for_client(client.id)
        by_vehicle: dict[int, list[OdometerReading]] = defaultdict(list)
        for r in await self.readings.for_vehicles([v.id for v in vehicles]):
            by_vehicle[r.vehicle_id].append(r)
        ids = []
        for vehicle in vehicles:
            history = _History(vehicle, by_vehicle[vehicle.id])
            reading = history.at((year, month))
            if reading is not None and reading.waybill is None:
                ids.append(await self._issue(vehicle, history, reading))
        await self.session.commit()
        return [await self.get_waybill(i) for i in ids]

    async def _waybill_out(
        self, waybill: Waybill, reading: OdometerReading, vehicle: Vehicle
    ) -> WaybillOut:
        client = await self.session.get(Client, vehicle.client_id)
        assert client is not None
        issuer = await self.session.get(User, waybill.issued_by) if waybill.issued_by else None
        return WaybillOut(
            id=waybill.id,
            number=waybill.number,
            year=reading.year,
            month=reading.month,
            client_id=client.id,
            client_name=client.name,
            client_idno=client.idno,
            vehicle_id=vehicle.id,
            plate=waybill.plate,
            model=waybill.model,
            fuel_type=waybill.fuel_type,
            driver=waybill.driver,
            fuel_norm=waybill.fuel_norm,
            start_odometer=waybill.start_odometer,
            end_odometer=waybill.end_odometer,
            km=waybill.end_odometer - waybill.start_odometer,
            fuel_liters=waybill.fuel_liters,
            issued_at=waybill.issued_at,
            issued_by_name=issuer.full_name if issuer else None,
        )

    async def _visible_waybill(self, waybill_id: int) -> tuple[Waybill, OdometerReading, Vehicle]:
        row = await self.waybills.get_full(waybill_id)
        if row is None:
            raise NotFoundError("Foaia de parcurs nu există")
        try:
            await self._client(row[2].client_id)
        except NotFoundError as e:
            raise NotFoundError("Foaia de parcurs nu există") from e
        return row

    async def get_waybill(self, waybill_id: int) -> WaybillOut:
        return await self._waybill_out(*await self._visible_waybill(waybill_id))

    async def list_waybills(self, client_id: int) -> list[WaybillOut]:
        client = await self._client(client_id)
        return [
            await self._waybill_out(*row) for row in await self.waybills.list_for_client(client.id)
        ]

    async def cancel_waybill(self, waybill_id: int) -> None:
        """Anulare: foaia se șterge (rămâne în jurnal), iar citirea se poate corecta."""
        waybill, _, _ = await self._visible_waybill(waybill_id)
        before = snapshot(waybill)
        async with conflict_guard(self.session, "Foaia de parcurs nu a putut fi anulată"):
            await self.session.delete(waybill)
        self.audit.deleted(waybill, before)
        await self.session.commit()
