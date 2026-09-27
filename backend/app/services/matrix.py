"""Matricea obligațiilor: ce rapoarte are fiecare client (client_report_types).

Reguli de reconciliere cu motorul de reguli:
- obligațiile `auto` urmează regulile: se adaugă cele noi, se dezactivează cele pe care
  regulile nu le mai dau;
- un tip de raport care are cel puțin o obligație `manual` (activă sau dezactivată) e decizia
  omului: recalcularea nu îl adaugă, nu îl dezactivează și nu îl modifică;
- dezactivarea unei obligații de către om (DELETE) o face `manual`, ca recalcularea următoare
  să n-o readauge.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Client,
    ClientReportType,
    ObligationSource,
    ReportType,
    User,
)
from app.repositories.classifier import ReportTypeRepository, RuleRepository
from app.repositories.matrix import ClientReportTypeRepository
from app.schemas.classifier import ReportTypeBrief
from app.schemas.matrix import ClientReportTypeCreate, RecalculateDiff
from app.services.audit import AuditService, snapshot
from app.services.errors import (
    ConflictError,
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)
from app.services.rules_engine import evaluate_client_reports


def _brief(report_type: ReportType) -> ReportTypeBrief:
    return ReportTypeBrief.model_validate(report_type)


@dataclass
class ReconcilePlan:
    client_id: int
    as_of: date
    to_add: list[ReportType]
    to_deactivate: list[ClientReportType]
    unchanged: list[ClientReportType]
    manual: list[ClientReportType]
    manual_excluded: list[ReportType]

    def to_diff(self) -> RecalculateDiff:
        return RecalculateDiff(
            client_id=self.client_id,
            as_of=self.as_of,
            to_add=[_brief(rt) for rt in self.to_add],
            to_deactivate=[_brief(r.report_type) for r in self.to_deactivate],
            unchanged=[_brief(r.report_type) for r in self.unchanged],
            manual=[_brief(r.report_type) for r in self.manual],
            manual_excluded=[_brief(rt) for rt in self.manual_excluded],
        )


class MatrixService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        self.session = session
        self.actor_id = actor.id if actor is not None else None
        self.audit = AuditService(session, actor)
        self.obligations = ClientReportTypeRepository(session)
        self.report_types = ReportTypeRepository(session)
        self.rules = RuleRepository(session)

    async def list_obligations(
        self, client: Client, active_only: bool = False
    ) -> Sequence[ClientReportType]:
        return await self.obligations.list_for_client(client.id, active_only)

    async def get_obligation(self, id_: int) -> ClientReportType:
        row = await self.obligations.get_with_report_type(id_)
        if row is None:
            raise NotFoundError("Obligația nu există")
        return row

    async def assign_manual(
        self, client: Client, data: ClientReportTypeCreate, today: date
    ) -> ClientReportType:
        report_type = await self.report_types.get(data.report_type_id)
        if report_type is None:
            raise ValidationFailedError("Tipul de raport nu există")
        if not report_type.is_active:
            raise ValidationFailedError("Tipul de raport e retras")
        valid_from = data.valid_from or today

        rows = [
            r
            for r in await self.obligations.list_for_client(client.id)
            if r.report_type_id == report_type.id
        ]
        if any(r.is_active for r in rows):
            raise ConflictError(f"{report_type.code} e deja atribuit clientului")

        same_day = next((r for r in rows if r.valid_from == valid_from), None)
        if same_day is not None:  # reactivare (unicitate pe client, raport, valid_from)
            before = snapshot(same_day)
            async with conflict_guard(self.session, "Obligația nu a putut fi salvată"):
                same_day.source = ObligationSource.MANUAL
                same_day.is_active = True
                same_day.valid_to = data.valid_to
                same_day.notes = data.notes
            self.audit.changed(same_day, before)
            await self.session.commit()
            return await self.get_obligation(same_day.id)

        row = ClientReportType(
            client_id=client.id,
            report_type_id=report_type.id,
            source=ObligationSource.MANUAL,
            valid_from=valid_from,
            valid_to=data.valid_to,
            notes=data.notes,
            created_by=self.actor_id,
        )
        async with conflict_guard(self.session, "Obligația nu a putut fi salvată"):
            self.obligations.add(row)
        self.audit.created(row)
        await self.session.commit()
        return await self.get_obligation(row.id)

    async def deactivate(self, row: ClientReportType, today: date) -> ClientReportType:
        """Dezactivare de către om. Devine `manual`, ca recalcularea să n-o readauge."""
        if not row.is_active:
            return row
        before = snapshot(row)
        async with conflict_guard(self.session, "Obligația nu a putut fi dezactivată"):
            row.is_active = False
            row.source = ObligationSource.MANUAL
            row.valid_to = max(today, row.valid_from)
        self.audit.changed(row, before)
        await self.session.commit()
        return await self.get_obligation(row.id)

    async def plan(self, client: Client, as_of: date) -> ReconcilePlan:
        """Ce ar schimba recalcularea. Nu scrie nimic."""
        rows = await self.obligations.list_for_client(client.id)
        manual_rows = [r for r in rows if r.source is ObligationSource.MANUAL]
        manual_types = {r.report_type_id for r in manual_rows}
        auto_active = {
            r.report_type_id: r
            for r in rows
            if r.source is ObligationSource.AUTO
            and r.is_active
            and r.report_type_id not in manual_types
        }

        rules = await self.rules.list_applicable(as_of)
        desired = set(evaluate_client_reports(client, rules))

        active_manual = [r for r in manual_rows if r.is_active]
        excluded_ids = manual_types - {r.report_type_id for r in active_manual}
        to_add_ids = desired - auto_active.keys() - manual_types
        return ReconcilePlan(
            client_id=client.id,
            as_of=as_of,
            to_add=list(await self.report_types.list_by_ids(to_add_ids)),
            to_deactivate=[r for rt, r in auto_active.items() if rt not in desired],
            unchanged=[r for rt, r in auto_active.items() if rt in desired],
            manual=active_manual,
            manual_excluded=list(await self.report_types.list_by_ids(excluded_ids)),
        )

    async def apply(self, client: Client, as_of: date) -> ReconcilePlan:
        """Recalculează și aplică. Planul se calculează din nou aici, nu se primește din
        exterior, ca schimbările de reguli de după previzualizare să fie luate în calcul."""
        plan = await self.plan(client, as_of)
        existing = await self.obligations.list_for_client(client.id)

        for report_type in plan.to_add:
            same_day = next(
                (
                    r
                    for r in existing
                    if r.report_type_id == report_type.id and r.valid_from == as_of
                ),
                None,
            )
            if same_day is not None:  # dezactivată azi, readăugată azi
                before = snapshot(same_day)
                async with conflict_guard(self.session, "Obligația nu a putut fi salvată"):
                    same_day.is_active = True
                    same_day.valid_to = None
                self.audit.changed(same_day, before)
                continue
            row = ClientReportType(
                client_id=client.id,
                report_type_id=report_type.id,
                source=ObligationSource.AUTO,
                valid_from=as_of,
                created_by=self.actor_id,
            )
            async with conflict_guard(self.session, "Obligația nu a putut fi salvată"):
                self.obligations.add(row)
            self.audit.created(row)

        for row in plan.to_deactivate:
            before = snapshot(row)
            async with conflict_guard(self.session, "Obligația nu a putut fi dezactivată"):
                row.is_active = False
                row.valid_to = max(as_of, row.valid_from)
            self.audit.changed(row, before)

        await self.session.commit()
        return plan
