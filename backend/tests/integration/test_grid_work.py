from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Client,
    ReportEntry,
    ReportTypeStep,
    Status,
    StatusSet,
    User,
    UserRole,
)
from app.schemas.grid import EntryUpdate
from app.seed.classifier import seed_classifier
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from app.services.grid import GridService, entry_out
from app.services.matrix import MatrixService
from tests.integration.factories import assign, make_client, make_user

NOW = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)


class Ctx:
    def __init__(self, session: AsyncSession, admin: User, ana: User, firm: Client) -> None:
        self.session, self.admin, self.ana, self.firm = session, admin, ana, firm

    def as_(self, user: User) -> GridService:
        return GridService(self.session, user)

    async def entry(self, code: str) -> ReportEntry:
        entry_id = await self.session.scalar(
            select(ReportEntry.id)
            .join(ReportEntry.report_type)
            .where(ReportEntry.client_id == self.firm.id)
            .where(ReportEntry.report_type.property.mapper.class_.code == code)
        )
        assert entry_id is not None
        return await self.as_(self.admin).get_entry(entry_id)

    async def status(self, set_code: str, code: str) -> int:
        status_id = await self.session.scalar(
            select(Status.id).join(StatusSet).where(StatusSet.code == set_code, Status.code == code)
        )
        assert status_id is not None
        return status_id

    @staticmethod
    def step(entry: ReportEntry, code: str) -> int:
        return next(s.step_id for s in entry.steps if s.step.code == code)


@pytest.fixture
async def ctx(session: AsyncSession) -> Ctx:
    await seed_classifier(session)
    admin = await make_user(session, "admin@birou.md", UserRole.ADMIN)
    ana = await make_user(session, "ana@birou.md", UserRole.CONTABIL)
    firm = await make_client(
        session, is_vat_payer=True, has_employees=True, is_it_park_resident=True
    )
    await assign(session, firm, ana)
    await MatrixService(session, admin).apply(firm, date(2026, 1, 1))
    await GridService(session, admin).generate(2026, 9)
    return Ctx(session, admin, ana, firm)


async def test_single_step_completion(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")
    step = ctx.step(tva, "transmitere")
    tva = await ctx.as_(ctx.ana).set_step_status(
        tva.id, step, await ctx.status("depunere", "transmis"), NOW
    )
    assert tva.is_completed is False
    tva = await ctx.as_(ctx.ana).set_step_status(
        tva.id, step, await ctx.status("depunere", "incarcat"), NOW
    )
    assert (tva.is_completed, tva.completed_at) == (True, NOW)
    assert tva.steps[0].changed_by == ctx.ana.id
    # înapoi la un status nefinal: nu mai e complet
    tva = await ctx.as_(ctx.ana).set_step_status(
        tva.id, step, await ctx.status("depunere", "transmis"), NOW
    )
    assert (tva.is_completed, tva.completed_at) == (False, None)


async def test_all_required_steps_needed(ctx: Ctx) -> None:
    iu17 = await ctx.entry("IU17")
    iu17 = await ctx.as_(ctx.admin).set_step_status(
        iu17.id,
        ctx.step(iu17, "transmitere"),
        await ctx.status("depunere", "incarcat"),
        NOW,
    )
    assert iu17.is_completed is False
    iu17 = await ctx.as_(ctx.admin).set_step_status(
        iu17.id,
        ctx.step(iu17, "inregistrare_1c"),
        await ctx.status("binar", "efectuat"),
        NOW,
    )
    assert iu17.is_completed is True


async def test_optional_step_not_needed(ctx: Ctx) -> None:
    iu17 = await ctx.entry("IU17")
    step_1c = await ctx.session.get(ReportTypeStep, ctx.step(iu17, "inregistrare_1c"))
    assert step_1c is not None
    step_1c.is_required = False
    await ctx.session.flush()
    iu17 = await ctx.as_(ctx.admin).set_step_status(
        iu17.id,
        ctx.step(iu17, "transmitere"),
        await ctx.status("depunere", "incarcat"),
        NOW,
    )
    assert iu17.is_completed is True


async def test_status_must_belong_to_step_set(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")
    with pytest.raises(ValidationFailedError, match="setului"):
        await ctx.as_(ctx.admin).set_step_status(
            tva.id,
            ctx.step(tva, "transmitere"),
            await ctx.status("binar", "efectuat"),
            NOW,
        )
    with pytest.raises(NotFoundError, match="etapă"):
        await ctx.as_(ctx.admin).set_step_status(tva.id, 999_999, 1, NOW)


async def test_audit_and_noop(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")
    step = ctx.step(tva, "transmitere")
    incarcat = await ctx.status("depunere", "incarcat")

    async def audited(entity: str) -> int:
        stmt = select(func.count()).where(
            AuditLog.entity_type == entity, AuditLog.action == "update"
        )
        return await ctx.session.scalar(stmt) or 0

    await ctx.as_(ctx.ana).set_step_status(tva.id, step, incarcat, NOW)
    assert (await audited("report_entry_steps"), await audited("report_entries")) == (1, 1)
    await ctx.as_(ctx.ana).set_step_status(tva.id, step, incarcat, NOW)  # același status
    assert await audited("report_entry_steps") == 1
    row = (
        await ctx.session.scalars(
            select(AuditLog)
            .where(AuditLog.entity_type == "report_entries")
            .order_by(AuditLog.id.desc())
        )
    ).first()
    assert row is not None and row.user_id == ctx.ana.id
    assert row.new_values is not None and row.new_values["is_completed"] is True


async def test_accountant_permissions(ctx: Ctx) -> None:
    ion = await make_user(ctx.session, "ion@birou.md", UserRole.CONTABIL)
    tva = await ctx.entry("TVA12")
    with pytest.raises(NotFoundError):
        await ctx.as_(ion).get_entry(tva.id)
    with pytest.raises(ForbiddenError, match="notițele"):
        await ctx.as_(ctx.ana).update_entry(tva.id, EntryUpdate(deadline=date(2026, 11, 1)))
    updated = await ctx.as_(ctx.ana).update_entry(tva.id, EntryUpdate(notes="sunat clientul"))
    assert updated.notes == "sunat clientul"


async def test_admin_updates_entry(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")
    with pytest.raises(ValidationFailedError, match="Utilizatorul"):
        await ctx.as_(ctx.admin).update_entry(tva.id, EntryUpdate(assigned_user_id=999_999))
    updated = await ctx.as_(ctx.admin).update_entry(
        tva.id, EntryUpdate(deadline=date(2026, 11, 2), assigned_user_id=None)
    )
    assert (updated.deadline, updated.assigned_user_id) == (date(2026, 11, 2), None)


async def test_closed_period_is_read_only(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")
    await ctx.as_(ctx.admin).set_period_closed(tva.period_id, True)
    with pytest.raises(ConflictError, match="închisă"):
        await ctx.as_(ctx.ana).set_step_status(
            tva.id,
            ctx.step(tva, "transmitere"),
            await ctx.status("depunere", "transmis"),
            NOW,
        )
    with pytest.raises(ConflictError):
        await ctx.as_(ctx.ana).update_entry(tva.id, EntryUpdate(notes="x"))
    await ctx.as_(ctx.admin).set_period_closed(tva.period_id, False)
    await ctx.as_(ctx.ana).update_entry(tva.id, EntryUpdate(notes="x"))


async def test_entry_out_overdue(ctx: Ctx) -> None:
    tva = await ctx.entry("TVA12")  # termen 26.10.2026
    assert entry_out(tva, date(2026, 10, 26)).is_overdue is False
    assert entry_out(tva, date(2026, 10, 27)).is_overdue is True
    extrase = await ctx.entry("EXTRASE")  # fără termen
    assert entry_out(extrase, date(2027, 1, 1)).is_overdue is False
    out = entry_out(await ctx.entry("IU17"), date(2026, 10, 1))
    assert [s.code for s in out.steps] == ["transmitere", "inregistrare_1c"]
