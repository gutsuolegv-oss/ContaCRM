from collections.abc import Sequence
from datetime import date

from fastapi import APIRouter, status

from app.api.deps import ClassifierEditor, CurrentUser, SessionDep
from app.core.clock import local_today
from app.models import Client, Periodicity, ReportRule, ReportType, ReportTypeStep
from app.schemas.classifier import (
    PreviewClientOut,
    ReportTypeCreate,
    ReportTypeDetailOut,
    ReportTypeOut,
    ReportTypeRetire,
    ReportTypeUpdate,
    RuleCreate,
    RuleOut,
    RuleUpdate,
    StepCreate,
    StepOut,
    StepUpdate,
)
from app.services.classifier import ClassifierService

router = APIRouter(tags=["clasificator: tipuri de rapoarte"])


@router.get("/report-types", response_model=list[ReportTypeOut])
async def list_report_types(
    session: SessionDep,
    user: CurrentUser,
    category_id: int | None = None,
    periodicity: Periodicity | None = None,
    active: bool | None = None,
) -> Sequence[ReportType]:
    return await ClassifierService(session, user).list_report_types(
        category_id, periodicity, active
    )


@router.post("/report-types", response_model=ReportTypeOut, status_code=status.HTTP_201_CREATED)
async def create_report_type(
    body: ReportTypeCreate, session: SessionDep, user: ClassifierEditor
) -> ReportType:
    return await ClassifierService(session, user).create_report_type(body)


@router.get("/report-types/{report_type_id}", response_model=ReportTypeDetailOut)
async def get_report_type(
    report_type_id: int, session: SessionDep, user: CurrentUser
) -> ReportType:
    """Detaliu, cu etape și reguli."""
    return await ClassifierService(session, user).get_report_type_detail(report_type_id)


@router.patch("/report-types/{report_type_id}", response_model=ReportTypeOut)
async def update_report_type(
    report_type_id: int, body: ReportTypeUpdate, session: SessionDep, user: ClassifierEditor
) -> ReportType:
    return await ClassifierService(session, user).update_report_type(report_type_id, body)


@router.post("/report-types/{report_type_id}/retire", response_model=ReportTypeOut)
async def retire_report_type(
    report_type_id: int, body: ReportTypeRetire, session: SessionDep, user: ClassifierEditor
) -> ReportType:
    """Setează valid_to și is_active = false. Tipurile de rapoarte nu se șterg niciodată."""
    return await ClassifierService(session, user).retire_report_type(report_type_id, body.valid_to)


# --- Etape ---


@router.post(
    "/report-types/{report_type_id}/steps",
    response_model=StepOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_step(
    report_type_id: int, body: StepCreate, session: SessionDep, user: ClassifierEditor
) -> ReportTypeStep:
    return await ClassifierService(session, user).create_step(report_type_id, body)


@router.patch("/steps/{step_id}", response_model=StepOut)
async def update_step(
    step_id: int, body: StepUpdate, session: SessionDep, user: ClassifierEditor
) -> ReportTypeStep:
    return await ClassifierService(session, user).update_step(step_id, body)


@router.delete("/steps/{step_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_step(step_id: int, session: SessionDep, user: ClassifierEditor) -> None:
    await ClassifierService(session, user).delete_step(step_id)


# --- Reguli ---


@router.get("/report-types/{report_type_id}/rules", response_model=list[RuleOut])
async def list_rules(
    report_type_id: int, session: SessionDep, user: CurrentUser
) -> Sequence[ReportRule]:
    return await ClassifierService(session, user).list_rules(report_type_id)


@router.post(
    "/report-types/{report_type_id}/rules",
    response_model=RuleOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_rule(
    report_type_id: int, body: RuleCreate, session: SessionDep, user: ClassifierEditor
) -> ReportRule:
    return await ClassifierService(session, user).create_rule(report_type_id, body)


@router.patch("/rules/{rule_id}", response_model=RuleOut)
async def update_rule(
    rule_id: int, body: RuleUpdate, session: SessionDep, user: ClassifierEditor
) -> ReportRule:
    return await ClassifierService(session, user).update_rule(rule_id, body)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rule(rule_id: int, session: SessionDep, user: ClassifierEditor) -> None:
    await ClassifierService(session, user).delete_rule(rule_id)


@router.post("/report-types/{report_type_id}/preview", response_model=list[PreviewClientOut])
async def preview(
    report_type_id: int,
    session: SessionDep,
    user: ClassifierEditor,
    as_of: date | None = None,
) -> list[Client]:
    """Clienții cărora li s-ar aplica raportul după regulile actuale. Nu scrie nimic.
    Doar pentru admin și director, pentru că listează toți clienții."""
    return await ClassifierService(session, user).preview(report_type_id, as_of or local_today())
