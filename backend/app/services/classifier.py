"""Clasificatorul de rapoarte: categorii, seturi de statusuri, tipuri, etape, reguli.

Fiecare scriere se înregistrează în audit_log. Tipurile de rapoarte nu se șterg niciodată:
se retrag (valid_to + is_active = false).
"""

from collections.abc import Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.models import (
    AuditAction,
    Client,
    Periodicity,
    ReportCategory,
    ReportRule,
    ReportType,
    ReportTypeStep,
    Status,
    StatusSet,
    User,
)
from app.repositories.classifier import (
    CategoryRepository,
    ReportTypeRepository,
    RuleRepository,
    StatusRepository,
    StatusSetRepository,
    StepRepository,
)
from app.repositories.client import ClientRepository
from app.schemas.classifier import (
    CategoryCreate,
    CategoryUpdate,
    ReportTypeCreate,
    ReportTypeUpdate,
    RuleCreate,
    RuleUpdate,
    StatusCreate,
    StatusSetCreate,
    StatusSetUpdate,
    StatusUpdate,
    StepCreate,
    StepUpdate,
    check_deadline_fields,
    check_valid_range,
)
from app.services.audit import AuditService, snapshot
from app.services.errors import (
    NotFoundError,
    ValidationFailedError,
    conflict_guard,
)
from app.services.rules_engine import decide_client_reports


def changes(data: BaseModel) -> dict[str, Any]:
    """Câmpurile trimise efectiv în PATCH (cele lipsă rămân neschimbate)."""
    return data.model_dump(exclude_unset=True)


def apply_changes(obj: Base, values: dict[str, Any]) -> None:
    """Aplică valorile; `null` pe o coloană obligatorie e refuzat cu mesaj clar."""
    columns = obj.__table__.columns
    for key, value in values.items():
        if value is None and not columns[key].nullable:
            raise ValidationFailedError(f"{key} nu poate fi gol")
        setattr(obj, key, value)


class ClassifierService:
    def __init__(self, session: AsyncSession, actor: User | None) -> None:
        self.session = session
        self.audit = AuditService(session, actor)
        self.categories = CategoryRepository(session)
        self.status_sets = StatusSetRepository(session)
        self.statuses = StatusRepository(session)
        self.report_types = ReportTypeRepository(session)
        self.steps = StepRepository(session)
        self.rules = RuleRepository(session)

    # --- ajutătoare ---

    async def _create(self, obj: Base, conflict: str) -> None:
        async with conflict_guard(self.session, conflict):
            self.session.add(obj)
        self.audit.created(obj)
        await self.session.commit()

    async def _update(
        self,
        obj: Base,
        values: dict[str, Any],
        conflict: str,
        action: AuditAction = AuditAction.UPDATE,
    ) -> None:
        before = snapshot(obj)
        async with conflict_guard(self.session, conflict):
            apply_changes(obj, values)
        self.audit.changed(obj, before, action)
        await self.session.commit()

    async def _delete(self, obj: Base, in_use: str) -> None:
        before = snapshot(obj)
        async with conflict_guard(self.session, in_use):
            await self.session.delete(obj)
        self.audit.deleted(obj, before)
        await self.session.commit()

    # --- Categorii ---

    async def list_categories(self, is_active: bool | None = None) -> Sequence[ReportCategory]:
        return await self.categories.list(is_active)

    async def get_category(self, id_: int) -> ReportCategory:
        category = await self.categories.get(id_)
        if category is None:
            raise NotFoundError("Categoria nu există")
        return category

    async def create_category(self, data: CategoryCreate) -> ReportCategory:
        category = ReportCategory(**data.model_dump())
        await self._create(category, f"Există deja o categorie cu codul {data.code}")
        return category

    async def update_category(self, id_: int, data: CategoryUpdate) -> ReportCategory:
        category = await self.get_category(id_)
        await self._update(category, changes(data), "Există deja o categorie cu acest cod")
        return category

    async def deactivate_category(self, id_: int) -> ReportCategory:
        category = await self.get_category(id_)
        await self._update(category, {"is_active": False}, "", AuditAction.DELETE)
        return category

    # --- Seturi de statusuri și statusuri ---

    async def list_status_sets(self) -> Sequence[StatusSet]:
        return await self.status_sets.list()

    async def get_status_set(self, id_: int) -> StatusSet:
        status_set = await self.status_sets.get_with_statuses(id_)
        if status_set is None:
            raise NotFoundError("Setul de statusuri nu există")
        return status_set

    async def create_status_set(self, data: StatusSetCreate) -> StatusSet:
        status_set = StatusSet(code=data.code, name=data.name)
        async with conflict_guard(self.session, f"Există deja un set cu codul {data.code}"):
            self.session.add(status_set)
        self.audit.created(status_set)
        for s in data.statuses:
            status = Status(status_set_id=status_set.id, **s.model_dump())
            async with conflict_guard(self.session, "Status invalid în set"):
                self.session.add(status)
            self.audit.created(status)
        await self.session.commit()
        return await self.get_status_set(status_set.id)

    async def update_status_set(self, id_: int, data: StatusSetUpdate) -> StatusSet:
        status_set = await self.get_status_set(id_)
        await self._update(status_set, changes(data), "Există deja un set cu acest cod")
        return await self.get_status_set(id_)

    async def get_status(self, id_: int) -> Status:
        status = await self.statuses.get(id_)
        if status is None:
            raise NotFoundError("Statusul nu există")
        return status

    async def create_status(self, status_set_id: int, data: StatusCreate) -> Status:
        await self.get_status_set(status_set_id)
        status = Status(status_set_id=status_set_id, **data.model_dump())
        await self._create(status, "Codul există deja în set, sau setul are deja un status inițial")
        return status

    async def update_status(self, id_: int, data: StatusUpdate) -> Status:
        status = await self.get_status(id_)
        await self._update(
            status, changes(data), "Codul există deja în set, sau setul are deja un status inițial"
        )
        return status

    async def delete_status(self, id_: int) -> None:
        status = await self.get_status(id_)
        await self._delete(status, "Statusul e folosit în grila de rapoarte și nu poate fi șters")

    # --- Tipuri de rapoarte ---

    async def list_report_types(
        self,
        category_id: int | None = None,
        periodicity: Periodicity | None = None,
        is_active: bool | None = None,
    ) -> Sequence[ReportType]:
        return await self.report_types.list(category_id, periodicity, is_active)

    async def get_report_type(self, id_: int) -> ReportType:
        report_type = await self.report_types.get(id_)
        if report_type is None:
            raise NotFoundError("Tipul de raport nu există")
        return report_type

    async def get_report_type_detail(self, id_: int) -> ReportType:
        report_type = await self.report_types.get_detail(id_)
        if report_type is None:
            raise NotFoundError("Tipul de raport nu există")
        return report_type

    async def _require_category(self, category_id: int) -> None:
        if await self.categories.get(category_id) is None:
            raise ValidationFailedError("Categoria nu există")

    async def create_report_type(self, data: ReportTypeCreate) -> ReportType:
        await self._require_category(data.category_id)
        report_type = ReportType(**data.model_dump())
        await self._create(
            report_type,
            f"Există deja tipul {data.code} valabil de la {data.valid_from.isoformat()}",
        )
        return report_type

    async def update_report_type(self, id_: int, data: ReportTypeUpdate) -> ReportType:
        report_type = await self.get_report_type(id_)
        values = changes(data)
        if values.get("category_id") is not None:
            await self._require_category(values["category_id"])

        # Verificările pe mai multe câmpuri, pe valorile combinate (vechi + noi).
        def merged(key: str) -> Any:
            return values[key] if key in values else getattr(report_type, key)

        try:
            if merged("deadline_rule") is not None:
                check_deadline_fields(
                    merged("deadline_rule"), merged("deadline_day"), merged("deadline_month")
                )
            check_valid_range(merged("valid_from"), merged("valid_to"))
        except ValueError as e:
            raise ValidationFailedError(str(e)) from e

        await self._update(
            report_type, values, "Există deja un tip cu acest cod și această dată de început"
        )
        return report_type

    async def retire_report_type(self, id_: int, valid_to: date) -> ReportType:
        """Retragere: nu se mai aplică după `valid_to`. Rândul rămâne pentru istoric."""
        report_type = await self.get_report_type(id_)
        if valid_to < report_type.valid_from:
            raise ValidationFailedError("valid_to nu poate fi înainte de valid_from")
        await self._update(
            report_type, {"valid_to": valid_to, "is_active": False}, "", AuditAction.RETIRE
        )
        return report_type

    # --- Etape ---

    async def get_step(self, id_: int) -> ReportTypeStep:
        step = await self.steps.get(id_)
        if step is None:
            raise NotFoundError("Etapa nu există")
        return step

    async def _require_status_set(self, status_set_id: int) -> None:
        if await self.status_sets.get(status_set_id) is None:
            raise ValidationFailedError("Setul de statusuri nu există")

    async def create_step(self, report_type_id: int, data: StepCreate) -> ReportTypeStep:
        await self.get_report_type(report_type_id)
        await self._require_status_set(data.status_set_id)
        step = ReportTypeStep(report_type_id=report_type_id, **data.model_dump())
        await self._create(step, f"Raportul are deja o etapă cu codul {data.code}")
        return step

    async def update_step(self, id_: int, data: StepUpdate) -> ReportTypeStep:
        step = await self.get_step(id_)
        values = changes(data)
        if values.get("status_set_id") is not None:
            await self._require_status_set(values["status_set_id"])
        await self._update(step, values, "Raportul are deja o etapă cu acest cod")
        return step

    async def delete_step(self, id_: int) -> None:
        step = await self.get_step(id_)
        await self._delete(step, "Etapa e folosită în grila de rapoarte și nu poate fi ștearsă")

    # --- Reguli ---

    async def list_rules(self, report_type_id: int) -> Sequence[ReportRule]:
        await self.get_report_type(report_type_id)
        return await self.rules.list_for_report_type(report_type_id)

    async def get_rule(self, id_: int) -> ReportRule:
        rule = await self.rules.get(id_)
        if rule is None:
            raise NotFoundError("Regula nu există")
        return rule

    async def create_rule(self, report_type_id: int, data: RuleCreate) -> ReportRule:
        await self.get_report_type(report_type_id)
        values = data.model_dump()
        values["conditions"] = data.conditions.to_json()
        rule = ReportRule(report_type_id=report_type_id, **values)
        await self._create(rule, "Regula nu a putut fi salvată")
        return rule

    async def update_rule(self, id_: int, data: RuleUpdate) -> ReportRule:
        rule = await self.get_rule(id_)
        values = changes(data)
        if data.conditions is not None:
            values["conditions"] = data.conditions.to_json()
        await self._update(rule, values, "Regula nu a putut fi salvată")
        return rule

    async def delete_rule(self, id_: int) -> None:
        rule = await self.get_rule(id_)
        await self._delete(rule, "Regula nu a putut fi ștearsă")

    async def preview(self, report_type_id: int, as_of: date) -> list[Client]:
        """Clienții activi cărora li s-ar aplica raportul la data `as_of`, după regulile
        actuale. Nu scrie nimic."""
        await self.get_report_type(report_type_id)
        rules = await self.rules.list_applicable(as_of, report_type_id)
        if not rules:
            return []
        clients = await ClientRepository(self.session).list_active()
        return [
            c
            for c in clients
            if (d := decide_client_reports(c, rules).get(report_type_id)) is not None and d.assigned
        ]
