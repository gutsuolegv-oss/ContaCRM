from collections import defaultdict
from collections.abc import Sequence
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import RecordStatus
from app.models import (
    Client,
    ClientAssignment,
    ClientReportType,
    PeriodType,
    ReportEntry,
    ReportEntryStep,
    ReportPeriod,
    ReportType,
    Status,
)
from app.repositories.base import Repository
from app.services.periods import PERIOD_TYPE_FOR


class PeriodRepository(Repository[ReportPeriod]):
    model = ReportPeriod

    async def get_by_key(
        self, period_type: PeriodType, year: int, period_no: int
    ) -> ReportPeriod | None:
        stmt = select(ReportPeriod).where(
            ReportPeriod.period_type == period_type,
            ReportPeriod.year == year,
            ReportPeriod.period_no == period_no,
        )
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_ending_in(self, year: int, month: int) -> Sequence[ReportPeriod]:
        start = date(year, month, 1)
        stmt = (
            select(ReportPeriod)
            .where(ReportPeriod.end_date >= start, ReportPeriod.end_date < _next_month(start))
            .order_by(ReportPeriod.start_date.desc())
        )
        return (await self.session.scalars(stmt)).all()


def _next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


class EntryRepository(Repository[ReportEntry]):
    model = ReportEntry

    async def existing_keys(self, period_id: int) -> set[tuple[int, int]]:
        """(client_id, report_type_id) ale celulelor deja generate pentru perioadă."""
        rows = await self.session.execute(
            select(ReportEntry.client_id, ReportEntry.report_type_id).where(
                ReportEntry.period_id == period_id
            )
        )
        return {(c, rt) for c, rt in rows}

    async def get_full(self, id_: int) -> ReportEntry | None:
        stmt = (
            select(ReportEntry)
            .where(ReportEntry.id == id_)
            .options(*_ENTRY_OPTIONS)
            .execution_options(populate_existing=True)
        )
        return (await self.session.scalars(stmt)).one_or_none()

    async def list_for_periods(
        self,
        period_ids: list[int],
        client_ids: set[int] | None = None,
        report_type_id: int | None = None,
        assigned_user_id: int | None = None,
        only_open: bool = False,
        overdue_on: date | None = None,
    ) -> Sequence[ReportEntry]:
        stmt = (
            select(ReportEntry)
            .join(Client, Client.id == ReportEntry.client_id)
            .join(ReportType, ReportType.id == ReportEntry.report_type_id)
            .where(ReportEntry.period_id.in_(period_ids))
            .options(*_ENTRY_OPTIONS)
            .order_by(Client.name, Client.id, ReportType.sort_order, ReportType.code)
        )
        if client_ids is not None:
            stmt = stmt.where(ReportEntry.client_id.in_(client_ids))
        if report_type_id is not None:
            stmt = stmt.where(ReportEntry.report_type_id == report_type_id)
        if assigned_user_id is not None:
            stmt = stmt.where(ReportEntry.assigned_user_id == assigned_user_id)
        if only_open or overdue_on is not None:
            stmt = stmt.where(ReportEntry.is_completed.is_(False))
        if overdue_on is not None:
            stmt = stmt.where(ReportEntry.deadline < overdue_on)
        return (await self.session.scalars(stmt)).all()


_ENTRY_OPTIONS = (
    selectinload(ReportEntry.client),
    selectinload(ReportEntry.report_type),
    selectinload(ReportEntry.period),
    selectinload(ReportEntry.steps).selectinload(ReportEntryStep.step),
    selectinload(ReportEntry.steps).selectinload(ReportEntryStep.status),
)


class EntryStepRepository(Repository[ReportEntryStep]):
    model = ReportEntryStep

    async def get_for_entry(self, entry_id: int, step_id: int) -> ReportEntryStep | None:
        stmt = select(ReportEntryStep).where(
            ReportEntryStep.entry_id == entry_id, ReportEntryStep.step_id == step_id
        )
        return (await self.session.scalars(stmt)).one_or_none()


class GenerationSourceRepository:
    """Datele de care are nevoie generarea grilei, citite dintr-o dată."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def obligations_for(
        self, period: ReportPeriod, report_types: Sequence[ReportType]
    ) -> Sequence[ClientReportType]:
        """Obligațiile clienților activi, pentru tipurile date, valabile măcar o zi din perioadă
        (după valid_from / valid_to, nu după is_active: o obligație dezactivată în octombrie
        a existat în septembrie)."""
        if not report_types:
            return []
        stmt = (
            select(ClientReportType)
            .join(Client, Client.id == ClientReportType.client_id)
            .where(
                ClientReportType.report_type_id.in_([rt.id for rt in report_types]),
                ClientReportType.valid_from <= period.end_date,
                or_(
                    ClientReportType.valid_to.is_(None),
                    ClientReportType.valid_to >= period.start_date,
                ),
                Client.status == RecordStatus.ACTIVE,
                Client.deleted_at.is_(None),
            )
        )
        return (await self.session.scalars(stmt)).all()

    async def active_obligations_starting_after(
        self, period: ReportPeriod, report_types: Sequence[ReportType]
    ) -> Sequence[ClientReportType]:
        """Obligații active care încep după perioadă: nu intră în grilă, dar le raportăm,
        ca să nu dispară neobservate (ex. prima recalculare făcută după lună)."""
        if not report_types:
            return []
        stmt = (
            select(ClientReportType)
            .join(Client, Client.id == ClientReportType.client_id)
            .where(
                ClientReportType.report_type_id.in_([rt.id for rt in report_types]),
                ClientReportType.is_active.is_(True),
                ClientReportType.valid_from > period.end_date,
                Client.status == RecordStatus.ACTIVE,
                Client.deleted_at.is_(None),
            )
        )
        return (await self.session.scalars(stmt)).all()

    async def report_types_for(self, period: ReportPeriod) -> Sequence[ReportType]:
        """Tipurile cu periodicitatea perioadei, valabile măcar o zi din ea, cu etapele lor."""
        periodicities = [p for p, t in PERIOD_TYPE_FOR.items() if t is period.period_type]
        stmt = (
            select(ReportType)
            .where(
                ReportType.periodicity.in_(periodicities),
                ReportType.valid_from <= period.end_date,
                or_(ReportType.valid_to.is_(None), ReportType.valid_to >= period.start_date),
            )
            .options(selectinload(ReportType.steps))
        )
        return (await self.session.scalars(stmt)).all()

    async def current_accountants(self, client_ids: set[int]) -> dict[int, list[int]]:
        if not client_ids:
            return {}
        rows = await self.session.execute(
            select(ClientAssignment.client_id, ClientAssignment.user_id).where(
                ClientAssignment.client_id.in_(client_ids),
                ClientAssignment.unassigned_at.is_(None),
            )
        )
        result: dict[int, list[int]] = defaultdict(list)
        for client_id, user_id in rows:
            result[client_id].append(user_id)
        return result

    async def initial_statuses(self, status_set_ids: set[int]) -> dict[int, int]:
        """Set de statusuri → statusul inițial."""
        if not status_set_ids:
            return {}
        rows = await self.session.execute(
            select(Status.status_set_id, Status.id).where(
                Status.status_set_id.in_(status_set_ids), Status.is_initial.is_(True)
            )
        )
        return dict(rows.tuples().all())
