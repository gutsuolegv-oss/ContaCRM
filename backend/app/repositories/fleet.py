from collections.abc import Sequence

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import selectinload

from app.db.base import RecordStatus
from app.models import OdometerReading, Vehicle, Waybill
from app.repositories.base import Repository

_ACTIVE = and_(Vehicle.status == RecordStatus.ACTIVE, Vehicle.deleted_at.is_(None))


class VehicleRepository(Repository[Vehicle]):
    model = Vehicle

    async def get_active(self, id_: int) -> Vehicle | None:
        stmt = select(Vehicle).where(Vehicle.id == id_, _ACTIVE)
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_for_client(self, client_id: int) -> Sequence[Vehicle]:
        stmt = (
            select(Vehicle)
            .where(Vehicle.client_id == client_id, _ACTIVE)
            .order_by(Vehicle.plate, Vehicle.id)
        )
        return (await self.session.scalars(stmt)).all()

    async def list_for_clients(self, client_ids: Sequence[int]) -> Sequence[Vehicle]:
        stmt = (
            select(Vehicle)
            .where(Vehicle.client_id.in_(client_ids), _ACTIVE)
            .order_by(Vehicle.client_id, Vehicle.plate, Vehicle.id)
        )
        return (await self.session.scalars(stmt)).all()


class ReadingRepository(Repository[OdometerReading]):
    model = OdometerReading

    async def for_vehicles(self, vehicle_ids: Sequence[int]) -> Sequence[OdometerReading]:
        """Toate citirile, cu foaia de parcurs, în ordine cronologică."""
        stmt = (
            select(OdometerReading)
            .where(OdometerReading.vehicle_id.in_(vehicle_ids))
            .options(selectinload(OdometerReading.waybill))
            .order_by(OdometerReading.vehicle_id, OdometerReading.year, OdometerReading.month)
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(stmt)).all()


class WaybillRepository(Repository[Waybill]):
    model = Waybill

    def _query(self) -> Select[tuple[Waybill, OdometerReading, Vehicle]]:
        return (
            select(Waybill, OdometerReading, Vehicle)
            .join(OdometerReading, Waybill.reading_id == OdometerReading.id)
            .join(Vehicle, OdometerReading.vehicle_id == Vehicle.id)
        )

    async def get_full(self, id_: int) -> tuple[Waybill, OdometerReading, Vehicle] | None:
        row = (await self.session.execute(self._query().where(Waybill.id == id_))).one_or_none()
        return None if row is None else (row[0], row[1], row[2])

    async def list_for_client(
        self, client_id: int
    ) -> list[tuple[Waybill, OdometerReading, Vehicle]]:
        """Cele mai recente primele."""
        stmt = (
            self._query()
            .where(Vehicle.client_id == client_id)
            .order_by(
                OdometerReading.year.desc(),
                OdometerReading.month.desc(),
                Waybill.number.desc(),
            )
        )
        return [(r[0], r[1], r[2]) for r in (await self.session.execute(stmt)).all()]

    async def numbers_with_prefix(self, prefix: str) -> Sequence[str]:
        stmt = select(Waybill.number).where(Waybill.number.startswith(prefix, autoescape=True))
        return (await self.session.scalars(stmt)).all()
