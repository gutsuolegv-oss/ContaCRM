from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditAction, AuditLog, Periodicity, User, UserRole
from app.schemas.classifier import (
    CategoryCreate,
    CategoryUpdate,
    ReportTypeCreate,
    ReportTypeUpdate,
    RuleCreate,
    RuleUpdate,
    StatusCreate,
    StatusSetCreate,
    StepCreate,
)
from app.services.classifier import ClassifierService
from app.services.errors import ConflictError, NotFoundError, ValidationFailedError
from tests.integration.factories import eq, make_classifier, make_client, make_user


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    return await make_user(session, "admin", UserRole.ADMIN)


@pytest.fixture
def service(session: AsyncSession, admin: User) -> ClassifierService:
    return ClassifierService(session, admin)


async def audit_rows(session: AsyncSession, entity_type: str) -> list[AuditLog]:
    stmt = select(AuditLog).where(AuditLog.entity_type == entity_type).order_by(AuditLog.id)
    return list((await session.scalars(stmt)).all())


# --- Categorii și audit ---


async def test_create_category_is_audited(
    session: AsyncSession, service: ClassifierService, admin: User
) -> None:
    cat = await service.create_category(CategoryCreate(code="plati", name="Plăți"))
    (row,) = await audit_rows(session, "report_categories")
    assert row.action is AuditAction.CREATE
    assert row.user_id == admin.id
    assert row.entity_id == cat.id
    assert row.old_values is None
    assert row.new_values is not None and row.new_values["code"] == "plati"


async def test_duplicate_code_conflict_keeps_session_usable(
    service: ClassifierService,
) -> None:
    await service.create_category(CategoryCreate(code="plati", name="Plăți"))
    with pytest.raises(ConflictError, match="plati"):
        await service.create_category(CategoryCreate(code="plati", name="Altă"))
    await service.create_category(CategoryCreate(code="altele", name="Altele"))
    assert len(await service.list_categories()) == 2


async def test_update_audits_only_changed_fields(
    session: AsyncSession, service: ClassifierService
) -> None:
    cat = await service.create_category(CategoryCreate(code="plati", name="Plăți"))
    await service.update_category(cat.id, CategoryUpdate(name="Plăți și impozite", sort_order=0))
    await service.update_category(cat.id, CategoryUpdate(name="Plăți și impozite"))  # nimic nou
    rows = await audit_rows(session, "report_categories")
    assert [r.action for r in rows] == [AuditAction.CREATE, AuditAction.UPDATE]
    assert rows[1].old_values == {"name": "Plăți"}
    assert rows[1].new_values == {"name": "Plăți și impozite"}


async def test_deactivate_category(session: AsyncSession, service: ClassifierService) -> None:
    cat = await service.create_category(CategoryCreate(code="plati", name="Plăți"))
    await service.deactivate_category(cat.id)
    assert cat.is_active is False
    assert [c.code for c in await service.list_categories(is_active=True)] == []
    rows = await audit_rows(session, "report_categories")
    assert rows[-1].action is AuditAction.DELETE
    assert rows[-1].new_values == {"is_active": False}


async def test_null_on_required_field(service: ClassifierService) -> None:
    cat = await service.create_category(CategoryCreate(code="plati", name="Plăți"))
    with pytest.raises(ValidationFailedError, match="name nu poate fi gol"):
        await service.update_category(cat.id, CategoryUpdate(name=None))


async def test_not_found(service: ClassifierService) -> None:
    with pytest.raises(NotFoundError):
        await service.update_category(999_999, CategoryUpdate(name="x"))


# --- Seturi de statusuri ---


async def test_status_set_with_statuses(service: ClassifierService) -> None:
    s = await service.create_status_set(
        StatusSetCreate(
            code="depunere",
            name="Depunere",
            statuses=[
                StatusCreate(code="neinceput", name="Neînceput", is_initial=True, sort_order=1),
                StatusCreate(code="incarcat", name="Încărcat", is_final=True, sort_order=3),
                StatusCreate(code="transmis", name="Transmis", sort_order=2),
            ],
        )
    )
    assert [st.code for st in s.statuses] == ["neinceput", "transmis", "incarcat"]
    with pytest.raises(ConflictError, match="status inițial"):
        await service.create_status(s.id, StatusCreate(code="x", name="X", is_initial=True))
    await service.delete_status(s.statuses[1].id)
    assert [st.code for st in (await service.get_status_set(s.id)).statuses] == [
        "neinceput",
        "incarcat",
    ]


# --- Tipuri de rapoarte ---


def _rt_data(category_id: int, **kw: object) -> ReportTypeCreate:
    fields: dict[str, object] = {
        "category_id": category_id,
        "code": "IU17",
        "name": "Impozit unic IT",
        "periodicity": "lunar",
        "deadline_rule": "day_of_next_period",
        "deadline_day": 25,
        "valid_from": "2026-01-01",
    }
    fields.update(kw)
    return ReportTypeCreate.model_validate(fields)


async def test_report_type_requires_existing_category(service: ClassifierService) -> None:
    with pytest.raises(ValidationFailedError, match="Categoria"):
        await service.create_report_type(_rt_data(999_999))


async def test_report_type_update_checks_merged_values(
    session: AsyncSession, service: ClassifierService
) -> None:
    c = await make_classifier(session)
    tva = c.id("TVA12")
    with pytest.raises(ValidationFailedError, match="deadline_month"):
        await service.update_report_type(tva, ReportTypeUpdate(deadline_rule="fixed_date"))
    with pytest.raises(ValidationFailedError, match="valid_to"):
        await service.update_report_type(tva, ReportTypeUpdate(valid_to=date(2025, 1, 1)))
    rt = await service.update_report_type(
        tva, ReportTypeUpdate(deadline_rule="fixed_date", deadline_month=3)
    )
    assert (rt.deadline_day, rt.deadline_month) == (25, 3)


async def test_new_version_of_same_code(session: AsyncSession, service: ClassifierService) -> None:
    c = await make_classifier(session)
    with pytest.raises(ConflictError, match="TVA12"):
        await service.create_report_type(_rt_data(c.category.id, code="TVA12"))
    await service.create_report_type(_rt_data(c.category.id, code="TVA12", valid_from="2027-01-01"))
    codes = [rt.code for rt in await service.list_report_types(periodicity=Periodicity.LUNAR)]
    assert codes.count("TVA12") == 2


async def test_retire(session: AsyncSession, service: ClassifierService) -> None:
    c = await make_classifier(session)
    with pytest.raises(ValidationFailedError):
        await service.retire_report_type(c.id("TVA12"), date(2025, 12, 31))
    rt = await service.retire_report_type(c.id("TVA12"), date(2026, 6, 30))
    assert (rt.is_active, rt.valid_to) == (False, date(2026, 6, 30))
    rows = await audit_rows(session, "report_types")
    assert rows[-1].action is AuditAction.RETIRE
    assert rows[-1].new_values == {"valid_to": "2026-06-30", "is_active": False}


# --- Etape și reguli ---


async def test_steps(session: AsyncSession, service: ClassifierService) -> None:
    c = await make_classifier(session)
    binar = await service.create_status_set(StatusSetCreate(code="binar", name="Binar"))
    with pytest.raises(ValidationFailedError, match="Setul"):
        await service.create_step(
            c.id("TL13"), StepCreate(status_set_id=999_999, code="transmitere", name="T")
        )
    await service.create_step(
        c.id("TL13"),
        StepCreate(status_set_id=binar.id, code="inregistrare_1c", name="1C", sort_order=2),
    )
    await service.create_step(
        c.id("TL13"), StepCreate(status_set_id=binar.id, code="transmitere", name="T", sort_order=1)
    )
    with pytest.raises(ConflictError, match="etapă"):
        await service.create_step(
            c.id("TL13"), StepCreate(status_set_id=binar.id, code="transmitere", name="T")
        )
    detail = await service.get_report_type_detail(c.id("TL13"))
    assert [s.code for s in detail.steps] == ["transmitere", "inregistrare_1c"]


async def test_rules_crud(session: AsyncSession, service: ClassifierService) -> None:
    c = await make_classifier(session)
    rule = await service.create_rule(
        c.id("TL13"),
        RuleCreate.model_validate(
            {"name": "Transport", "action": "assign", "conditions": eq("has_transport", True)}
        ),
    )
    assert rule.conditions == eq("has_transport", True)
    await service.update_rule(
        rule.id, RuleUpdate.model_validate({"conditions": eq("has_employees", True)})
    )
    assert rule.conditions == eq("has_employees", True)
    await service.delete_rule(rule.id)
    assert await service.list_rules(c.id("TL13")) == []
    actions = [r.action for r in await audit_rows(session, "report_rules")]
    assert actions == [AuditAction.CREATE, AuditAction.UPDATE, AuditAction.DELETE]


async def test_preview(session: AsyncSession, service: ClassifierService) -> None:
    c = await make_classifier(session)
    vat = await make_client(session, "1000000000001", is_vat_payer=True)
    await make_client(session, "1000000000002")
    before = await session.scalar(select(func.count()).select_from(AuditLog))

    clients = await service.preview(c.id("TVA12"), date(2026, 9, 1))
    assert [cl.id for cl in clients] == [vat.id]
    assert len(await service.preview(c.id("EXTRASE"), date(2026, 9, 1))) == 2
    assert await service.preview(c.id("TL13"), date(2026, 9, 1)) == []  # fără reguli
    await service.retire_report_type(c.id("TVA12"), date(2026, 6, 30))
    assert await service.preview(c.id("TVA12"), date(2026, 9, 1)) == []
    # previzualizarea n-a scris nimic (doar retragerea, 1 rând de audit)
    after = await session.scalar(select(func.count()).select_from(AuditLog))
    assert after == (before or 0) + 1
