"""Schemele API pentru obligațiile clienților (matricea) și recalculare."""

from datetime import date, datetime
from typing import Self

from pydantic import model_validator

from app.models import ObligationSource
from app.schemas.classifier import ReportTypeBrief, check_valid_range
from app.schemas.common import InputModel, ORMModel


class ClientReportTypeCreate(InputModel):
    """Atribuire manuală (source = manual). Fără valid_from: de azi."""

    report_type_id: int
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        check_valid_range(self.valid_from, self.valid_to)
        return self


class ClientReportTypeOut(ORMModel):
    id: int
    client_id: int
    report_type: ReportTypeBrief
    source: ObligationSource
    is_active: bool
    valid_from: date
    valid_to: date | None
    notes: str | None
    created_by: int | None
    created_at: datetime


class RecalculateDiff(ORMModel):
    """Rezultatul motorului de reguli comparat cu obligațiile actuale ale clientului.

    to_add: rapoarte noi, de atribuit automat
    to_deactivate: obligații automate pe care regulile nu le mai dau
    unchanged: obligații automate confirmate de reguli
    manual: atribuite manual; recalcularea nu le atinge
    manual_excluded: dezactivate de om; recalcularea nu le readaugă
    """

    client_id: int
    as_of: date
    to_add: list[ReportTypeBrief]
    to_deactivate: list[ReportTypeBrief]
    unchanged: list[ReportTypeBrief]
    manual: list[ReportTypeBrief]
    manual_excluded: list[ReportTypeBrief]
