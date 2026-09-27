"""Grila de execuție: o celulă pentru fiecare client, raport și perioadă, cu statusurile etapelor.

Grila unei luni conține toate perioadele care SE TERMINĂ în acea lună (septembrie: lunar 9 și
trimestrul III). Generarea adaugă doar celulele care lipsesc și nu le atinge pe cele existente;
nici nu șterge celule când obligațiile clientului se schimbă (asta o face omul).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ReportEntry,
    ReportEntryStep,
    ReportPeriod,
    ReportType,
    Status,
    User,
    UserRole,
)
from app.repositories.client import AssignmentRepository, ClientRepository
from app.repositories.execution import (
    EntryRepository,
    GenerationSourceRepository,
    PeriodRepository,
)
from app.repositories.holiday import HolidayRepository
from app.repositories.user import UserRepository
from app.schemas.classifier import ReportTypeBrief
from app.schemas.grid import (
    AccountantBrief,
    ClientBrief,
    EntryOut,
    EntryStepOut,
    EntryUpdate,
    GridOut,
    GridRowOut,
    PeriodOut,
    StatusBrief,
)
from app.services.access import SEES_ALL_CLIENTS
from app.services.audit import AuditService, snapshot
from app.services.deadlines import calculate_deadline
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)
from app.services.fleet import month_summaries
from app.services.periods import period_bounds, periods_ending_in

# Termenul poate fi cu până la 24 de luni după sfârșitul perioadei (deadline_month_offset).
_CALENDAR_SPAN = timedelta(days=24 * 31 + 31)


@dataclass
class PeriodGeneration:
    period: ReportPeriod
    created: int = 0
    existing: int = 0
    closed: bool = False
    # (client_id, report_type_id): obligații active care încep după perioadă, deci nu intră
    # în grila ei. Semn că recalcularea s-a făcut cu o dată prea târzie (as_of).
    starting_later: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class GenerationResult:
    year: int
    month: int
    periods: list[PeriodGeneration]

    @property
    def created(self) -> int:
        return sum(p.created for p in self.periods)


def is_complete(steps: Sequence[ReportEntryStep]) -> bool:
    """Complet: există etape, iar toate cele obligatorii (sau toate, dacă niciuna nu e
    obligatorie) sunt pe un status final."""
    if not steps:
        return False
    required = [s for s in steps if s.step.is_required] or list(steps)
    return all(s.status.is_final for s in required)


def entry_out(entry: ReportEntry, today: date) -> EntryOut:
    """Celula pentru API, cu `is_overdue` calculat față de `today`."""
    return EntryOut(
        id=entry.id,
        client_id=entry.client_id,
        report_type_id=entry.report_type_id,
        period_id=entry.period_id,
        deadline=entry.deadline,
        assigned_user_id=entry.assigned_user_id,
        is_completed=entry.is_completed,
        completed_at=entry.completed_at,
        is_overdue=(
            not entry.is_completed and entry.deadline is not None and entry.deadline < today
        ),
        notes=entry.notes,
        steps=[
            EntryStepOut(
                step_id=s.step_id,
                status_set_id=s.step.status_set_id,
                code=s.step.code,
                name=s.step.name,
                is_required=s.step.is_required,
                status=StatusBrief.model_validate(s.status),
                changed_by=s.changed_by,
                changed_at=s.changed_at,
            )
            for s in sorted(entry.steps, key=lambda s: (s.step.sort_order, s.step.id))
        ],
    )


class GridService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        """`actor`: cine face acțiunea — pentru permisiuni și pentru audit_log. `None` doar
        pentru acțiunile sistemului (generarea automată)."""
        self.session = session
        self.actor = actor
        self.actor_id = actor.id if actor is not None else None
        self.audit = AuditService(session, actor)
        self.periods = PeriodRepository(session)
        self.entries = EntryRepository(session)
        self.sources = GenerationSourceRepository(session)

    async def ensure_periods(self, year: int, month: int) -> list[ReportPeriod]:
        """Perioadele care se termină în luna dată; le creează pe cele care lipsesc."""
        result = []
        for period_type, period_no in periods_ending_in(month):
            period = await self.periods.get_by_key(period_type, year, period_no)
            if period is None:
                start, end = period_bounds(period_type, year, period_no)
                period = ReportPeriod(
                    period_type=period_type,
                    year=year,
                    period_no=period_no,
                    start_date=start,
                    end_date=end,
                )
                async with conflict_guard(self.session, "Perioada există deja"):
                    self.periods.add(period)
                self.audit.created(period)
            result.append(period)
        return result

    async def generate(self, year: int, month: int) -> GenerationResult:
        periods = await self.ensure_periods(year, month)
        first_end = min(p.end_date for p in periods)
        calendar = await HolidayRepository(self.session).load_calendar(
            first_end, first_end + _CALENDAR_SPAN
        )
        result = GenerationResult(year, month, [])
        for period in periods:
            outcome = PeriodGeneration(period, closed=period.is_closed)
            result.periods.append(outcome)
            if period.is_closed:
                continue

            types = await self.sources.report_types_for(period)
            by_id = {rt.id: rt for rt in types}
            obligations = await self.sources.obligations_for(period, types)
            wanted = {(o.client_id, o.report_type_id) for o in obligations}
            existing = await self.entries.existing_keys(period.id)
            missing = sorted(wanted - existing)
            outcome.existing = len(wanted & existing)

            later = await self.sources.active_obligations_starting_after(period, types)
            outcome.starting_later = sorted(
                {(o.client_id, o.report_type_id) for o in later} - wanted - existing
            )
            if not missing:
                continue

            used_types = [by_id[rt_id] for _, rt_id in missing]
            initial = await self._initial_statuses(used_types)
            accountants = await self.sources.current_accountants({c for c, _ in missing})
            for client_id, rt_id in missing:
                report_type = by_id[rt_id]
                users = accountants.get(client_id, [])
                entry = ReportEntry(
                    client_id=client_id,
                    report_type_id=rt_id,
                    period_id=period.id,
                    deadline=calculate_deadline(report_type, period, calendar),
                    # un singur contabil: el; mai mulți sau niciunul: se alege manual
                    assigned_user_id=users[0] if len(users) == 1 else None,
                    steps=[
                        ReportEntryStep(
                            step_id=step.id,
                            status_id=initial[step.status_set_id],
                            changed_by=self.actor_id,
                        )
                        for step in report_type.steps
                    ],
                )
                async with conflict_guard(self.session, "Celula există deja"):
                    self.entries.add(entry)
                self.audit.created(entry)
                outcome.created += 1
        await self.session.commit()
        return result

    async def _initial_statuses(self, report_types: Sequence[ReportType]) -> dict[int, int]:
        set_ids = {step.status_set_id for rt in report_types for step in rt.steps}
        initial = await self.sources.initial_statuses(set_ids)
        for rt in report_types:
            for step in rt.steps:
                if step.status_set_id not in initial:
                    raise ValidationFailedError(
                        f"Etapa {rt.code}/{step.code}: setul ei de statusuri nu are "
                        "un status inițial"
                    )
        return initial

    # --- Vizualizarea grilei ---

    async def view(
        self,
        year: int,
        month: int,
        today: date,
        client_id: int | None = None,
        report_type_id: int | None = None,
        assigned_user_id: int | None = None,
        only_open: bool = False,
        only_overdue: bool = False,
    ) -> GridOut:
        """Grila lunii: un rând pe client, o celulă pe raport și perioadă. Contabilul vede doar
        clienții repartizați lui."""
        periods = await self.periods.list_ending_in(year, month)
        client_ids: set[int] | None = None
        if self._user().role not in SEES_ALL_CLIENTS:
            client_ids = await ClientRepository(self.session).assigned_ids(self._user().id)
        if client_id is not None:
            client_ids = {client_id} if client_ids is None else client_ids & {client_id}

        entries = (
            await self.entries.list_for_periods(
                [p.id for p in periods],
                client_ids=client_ids,
                report_type_id=report_type_id,
                assigned_user_id=assigned_user_id,
                only_open=only_open,
                overdue_on=today if only_overdue else None,
            )
            if periods
            else []
        )

        rows: dict[int, GridRowOut] = {}
        columns: dict[int, ReportType] = {}
        for entry in entries:
            row = rows.get(entry.client_id)
            if row is None:
                row = GridRowOut(client=ClientBrief.model_validate(entry.client), entries=[])
                rows[entry.client_id] = row
            row.entries.append(entry_out(entry, today))
            columns[entry.report_type_id] = entry.report_type
        if rows:
            assignments = await AssignmentRepository(self.session).current_for_clients(list(rows))
            for a in assignments:
                rows[a.client_id].accountants.append(AccountantBrief.model_validate(a.user))
            fleets = await month_summaries(self.session, list(rows), year, month, today)
            for client_id, fleet in fleets.items():
                rows[client_id].fleet = fleet
        ordered = sorted(columns.values(), key=lambda rt: (rt.sort_order, rt.code, rt.id))
        return GridOut(
            year=year,
            month=month,
            periods=[PeriodOut.model_validate(p) for p in periods],
            report_types=[ReportTypeBrief.model_validate(rt) for rt in ordered],
            rows=list(rows.values()),
        )

    # --- Lucrul pe celule ---

    def _user(self) -> User:
        if self.actor is None:
            raise ForbiddenError("Acțiune permisă doar unui utilizator")
        return self.actor

    async def get_entry(self, entry_id: int) -> ReportEntry:
        """Celula, dacă utilizatorul o poate vedea (contabilul: doar la clienții lui)."""
        entry = await self.entries.get_full(entry_id)
        if entry is None or not await self.sees_client(entry.client_id):
            raise NotFoundError("Celula nu există")
        return entry

    async def sees_client(self, client_id: int) -> bool:
        user = self._user()
        if user.role in SEES_ALL_CLIENTS:
            return True
        return await ClientRepository(self.session).is_assigned_to(client_id, user.id)

    @staticmethod
    def _ensure_open(entry: ReportEntry) -> None:
        if entry.period.is_closed:
            raise ConflictError("Perioada e închisă; redeschide-o ca să modifici")

    async def set_step_status(
        self, entry_id: int, step_id: int, status_id: int, now: datetime
    ) -> ReportEntry:
        entry = await self.get_entry(entry_id)
        self._ensure_open(entry)
        entry_step = next((s for s in entry.steps if s.step_id == step_id), None)
        if entry_step is None:
            raise NotFoundError("Raportul nu are această etapă")
        status = await self.session.get(Status, status_id)
        if status is None or status.status_set_id != entry_step.step.status_set_id:
            raise ValidationFailedError("Statusul nu aparține setului de statusuri al etapei")
        if entry_step.status_id == status.id:
            return entry

        step_before, entry_before = snapshot(entry_step), snapshot(entry)
        async with conflict_guard(self.session, "Statusul nu a putut fi salvat"):
            entry_step.status = status
            entry_step.changed_by = self.actor_id
            entry_step.changed_at = now
            complete = is_complete(entry.steps)
            if complete != entry.is_completed:
                entry.is_completed = complete
                entry.completed_at = now if complete else None
        self.audit.changed(entry_step, step_before)
        self.audit.changed(entry, entry_before)
        await self.session.commit()
        return await self.get_entry(entry_id)

    async def update_entry(self, entry_id: int, data: EntryUpdate) -> ReportEntry:
        entry = await self.get_entry(entry_id)
        self._ensure_open(entry)
        values = data.model_dump(exclude_unset=True)
        if self._user().role is UserRole.CONTABIL and set(values) - {"notes"}:
            raise ForbiddenError("Contabilul poate modifica doar notițele")
        if values.get("assigned_user_id") is not None:
            if await UserRepository(self.session).get_active(values["assigned_user_id"]) is None:
                raise ValidationFailedError("Utilizatorul nu există")

        before = snapshot(entry)
        async with conflict_guard(self.session, "Celula nu a putut fi salvată"):
            for key, value in values.items():
                setattr(entry, key, value)
        self.audit.changed(entry, before)
        await self.session.commit()
        return await self.get_entry(entry_id)

    # --- Perioade ---

    async def set_period_closed(self, period_id: int, closed: bool) -> ReportPeriod:
        period = await self.periods.get(period_id)
        if period is None:
            raise NotFoundError("Perioada nu există")
        before = snapshot(period)
        async with conflict_guard(self.session, "Perioada nu a putut fi salvată"):
            period.is_closed = closed
        self.audit.changed(period, before)
        await self.session.commit()
        return period
