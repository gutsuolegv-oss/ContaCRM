"""Schemele API pentru grila de execuție (/api/grid)."""

from datetime import date, datetime

from pydantic import Field

from app.models import PeriodType
from app.schemas.classifier import ReportTypeBrief
from app.schemas.common import InputModel, ORMModel


class EntryUpdate(InputModel):
    """Contabilul poate trimite doar `notes`; restul, admin și director."""

    deadline: date | None = None
    assigned_user_id: int | None = None
    notes: str | None = Field(default=None, max_length=5000)


class StepStatusIn(InputModel):
    status_id: int


class StatusBrief(ORMModel):
    id: int
    code: str
    name: str
    is_final: bool


class EntryStepOut(ORMModel):
    step_id: int
    code: str
    name: str
    is_required: bool
    status: StatusBrief
    changed_by: int | None
    changed_at: datetime


class EntryOut(ORMModel):
    id: int
    client_id: int
    report_type_id: int
    period_id: int
    deadline: date | None
    assigned_user_id: int | None
    is_completed: bool
    completed_at: datetime | None
    is_overdue: bool
    notes: str | None
    steps: list[EntryStepOut]


class PeriodOut(ORMModel):
    id: int
    period_type: PeriodType
    year: int
    period_no: int
    start_date: date
    end_date: date
    is_closed: bool


class ClientBrief(ORMModel):
    id: int
    name: str
    idno: str


class GridRowOut(ORMModel):
    client: ClientBrief
    entries: list[EntryOut]


class GridOut(ORMModel):
    year: int
    month: int
    periods: list[PeriodOut]
    report_types: list[ReportTypeBrief]  # coloanele: doar cele care apar în rânduri
    rows: list[GridRowOut]


class PeriodGenerationOut(ORMModel):
    period: PeriodOut
    created: int
    existing: int
    closed: bool
    starting_later: list[tuple[int, int]]  # (client_id, report_type_id)


class GenerationOut(ORMModel):
    year: int
    month: int
    created: int
    periods: list[PeriodGenerationOut]
