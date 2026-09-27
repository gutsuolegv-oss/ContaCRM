"""Grila de execuție: o celulă pentru fiecare client, raport și perioadă, cu statusurile etapelor.

Grila unei luni conține toate perioadele care SE TERMINĂ în acea lună (septembrie: lunar 9 și
trimestrul III). Generarea adaugă doar celulele care lipsesc și nu le atinge pe cele existente;
nici nu șterge celule când obligațiile clientului se schimbă (asta o face omul).
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    ReportEntry,
    ReportEntryStep,
    ReportPeriod,
    ReportType,
    User,
)
from app.repositories.execution import (
    EntryRepository,
    GenerationSourceRepository,
    PeriodRepository,
)
from app.repositories.holiday import HolidayRepository
from app.services.audit import AuditService
from app.services.deadlines import calculate_deadline
from app.services.errors import ValidationFailedError, conflict_guard
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


class GridService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        self.session = session
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
