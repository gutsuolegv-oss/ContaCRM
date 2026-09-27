"""Schemele API pentru /api/classifiers."""

import calendar
from datetime import date, datetime
from typing import Annotated, Self

from pydantic import Field, field_validator, model_validator

from app.models import DeadlineRule, Periodicity, RuleAction
from app.schemas.common import Code, InputModel, Name100, Name200, Name255, ORMModel
from app.schemas.conditions import ConditionGroup


def check_deadline_fields(rule: DeadlineRule, day: int | None, month: int | None) -> None:
    """Aceleași reguli ca CHECK-urile din report_types. Serviciul o apelează și la PATCH,
    pe valorile combinate (vechi + noi)."""
    if rule is DeadlineRule.DAY_OF_NEXT_PERIOD and day is None:
        raise ValueError("day_of_next_period cere deadline_day")
    if rule is DeadlineRule.FIXED_DATE:
        if day is None or month is None:
            raise ValueError("fixed_date cere deadline_day și deadline_month")
        # an bisect, ca 29 februarie să fie permis
        if day > calendar.monthrange(2024, month)[1]:
            raise ValueError(f"luna {month} nu are ziua {day}")


def check_valid_range(valid_from: date | None, valid_to: date | None) -> None:
    if valid_from is not None and valid_to is not None and valid_to < valid_from:
        raise ValueError("valid_to nu poate fi înainte de valid_from")


Day = Annotated[int, Field(ge=1, le=31)]
Month = Annotated[int, Field(ge=1, le=12)]
NotifyDays = Annotated[list[Annotated[int, Field(ge=0, le=365)]], Field(max_length=10)]


def _normalize_notify(days: list[int] | None) -> list[int] | None:
    """Fără dubluri, descrescător: [1, 7, 3, 7] → [7, 3, 1]."""
    return None if days is None else sorted(set(days), reverse=True)


# --- Categorii ---


class CategoryCreate(InputModel):
    code: Code
    name: Name200
    description: str | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(InputModel):
    code: Code | None = None
    name: Name200 | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class CategoryOut(ORMModel):
    id: int
    code: str
    name: str
    description: str | None
    sort_order: int
    is_active: bool


# --- Seturi de statusuri ---


class StatusCreate(InputModel):
    code: Code
    name: Name100
    is_initial: bool = False
    is_final: bool = False
    sort_order: int = 0


class StatusUpdate(InputModel):
    code: Code | None = None
    name: Name100 | None = None
    is_initial: bool | None = None
    is_final: bool | None = None
    sort_order: int | None = None


class StatusOut(ORMModel):
    id: int
    status_set_id: int
    code: str
    name: str
    is_initial: bool
    is_final: bool
    sort_order: int


class StatusSetCreate(InputModel):
    code: Code
    name: Name200
    statuses: list[StatusCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_statuses(self) -> Self:
        codes = [s.code for s in self.statuses]
        if len(codes) != len(set(codes)):
            raise ValueError("coduri de status duplicate")
        if sum(s.is_initial for s in self.statuses) > 1:
            raise ValueError("cel mult un status inițial")
        return self


class StatusSetUpdate(InputModel):
    code: Code | None = None
    name: Name200 | None = None


class StatusSetOut(ORMModel):
    id: int
    code: str
    name: str
    statuses: list[StatusOut]


# --- Etape ---


class StepCreate(InputModel):
    status_set_id: int
    code: Code
    name: Name100
    is_required: bool = True
    sort_order: int = 0


class StepUpdate(InputModel):
    status_set_id: int | None = None
    code: Code | None = None
    name: Name100 | None = None
    is_required: bool | None = None
    sort_order: int | None = None


class StepOut(ORMModel):
    id: int
    report_type_id: int
    status_set_id: int
    code: str
    name: str
    is_required: bool
    sort_order: int


# --- Reguli ---


class RuleCreate(InputModel):
    name: Name200
    conditions: ConditionGroup = Field(default_factory=ConditionGroup)
    action: RuleAction
    priority: int = 100
    is_active: bool = True


class RuleUpdate(InputModel):
    name: Name200 | None = None
    conditions: ConditionGroup | None = None
    action: RuleAction | None = None
    priority: int | None = None
    is_active: bool | None = None


class RuleOut(ORMModel):
    id: int
    report_type_id: int
    name: str
    conditions: ConditionGroup
    action: RuleAction
    priority: int
    is_active: bool


# --- Tipuri de rapoarte ---


class ReportTypeCreate(InputModel):
    category_id: int
    code: Code
    name: Name255
    full_name: str | None = None
    legal_reference: str | None = None
    authority: Annotated[str, Field(max_length=100)] | None = None
    periodicity: Periodicity
    deadline_rule: DeadlineRule
    deadline_day: Day | None = None
    deadline_month: Month | None = None
    requires_payment: bool = False
    notify_days_before: NotifyDays = Field(default_factory=lambda: [7, 3, 1])
    valid_from: date
    valid_to: date | None = None
    is_active: bool = True
    sort_order: int = 0

    _normalize = field_validator("notify_days_before")(_normalize_notify)

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_deadline_fields(self.deadline_rule, self.deadline_day, self.deadline_month)
        check_valid_range(self.valid_from, self.valid_to)
        return self


class ReportTypeUpdate(InputModel):
    """Verificările care implică mai multe câmpuri se fac în serviciu, pe valorile combinate."""

    category_id: int | None = None
    code: Code | None = None
    name: Name255 | None = None
    full_name: str | None = None
    legal_reference: str | None = None
    authority: Annotated[str, Field(max_length=100)] | None = None
    periodicity: Periodicity | None = None
    deadline_rule: DeadlineRule | None = None
    deadline_day: Day | None = None
    deadline_month: Month | None = None
    requires_payment: bool | None = None
    notify_days_before: NotifyDays | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    _normalize = field_validator("notify_days_before")(_normalize_notify)


class ReportTypeRetire(InputModel):
    valid_to: date


class ReportTypeOut(ORMModel):
    id: int
    category_id: int
    code: str
    name: str
    full_name: str | None
    legal_reference: str | None
    authority: str | None
    periodicity: Periodicity
    deadline_rule: DeadlineRule
    deadline_day: int | None
    deadline_month: int | None
    requires_payment: bool
    notify_days_before: list[int]
    valid_from: date
    valid_to: date | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime


class ReportTypeDetailOut(ReportTypeOut):
    steps: list[StepOut]
    rules: list[RuleOut]


class ReportTypeBrief(ORMModel):
    id: int
    code: str
    name: str


class PreviewClientOut(ORMModel):
    id: int
    name: str
    idno: str
