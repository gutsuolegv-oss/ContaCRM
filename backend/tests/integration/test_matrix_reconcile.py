from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AuditLog,
    Client,
    ClientReportType,
    ObligationSource,
    User,
    UserRole,
)
from app.schemas.classifier import ReportTypeBrief
from app.schemas.matrix import ClientReportTypeCreate
from app.services.access import get_visible_client
from app.services.errors import ConflictError, NotFoundError, ValidationFailedError
from app.services.matrix import MatrixService
from tests.integration.factories import Classifier, assign, make_classifier, make_client, make_user

DAY1 = date(2026, 9, 1)
DAY2 = date(2026, 10, 1)


@pytest.fixture
async def admin(session: AsyncSession) -> User:
    return await make_user(session, "admin@birou.md", UserRole.ADMIN)


@pytest.fixture
async def classifier(session: AsyncSession) -> Classifier:
    return await make_classifier(session)


@pytest.fixture
async def client(session: AsyncSession) -> Client:  # suprascrie fixture-ul HTTP `client`
    return await make_client(session, is_vat_payer=True, has_employees=True)


@pytest.fixture
def service(session: AsyncSession, admin: User) -> MatrixService:
    return MatrixService(session, admin)


def codes(briefs: list[ReportTypeBrief]) -> list[str]:
    return sorted(b.code for b in briefs)


async def active_codes(service: MatrixService, client: Client) -> dict[str, ObligationSource]:
    rows = await service.list_obligations(client, active_only=True)
    return {r.report_type.code: r.source for r in rows}


async def test_plan_writes_nothing(
    session: AsyncSession, service: MatrixService, client: Client, classifier: Classifier
) -> None:
    diff = (await service.plan(client, DAY1)).to_diff()
    assert codes(diff.to_add) == ["EXTRASE", "IPC21", "TVA12"]
    assert diff.to_deactivate == diff.unchanged == diff.manual == []
    count = await session.scalar(select(func.count()).select_from(ClientReportType))
    assert count == 0


async def test_first_apply_adds_auto_obligations(
    session: AsyncSession, service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    assert await active_codes(service, client) == {
        "EXTRASE": ObligationSource.AUTO,
        "IPC21": ObligationSource.AUTO,
        "TVA12": ObligationSource.AUTO,
    }
    rows = await service.list_obligations(client)
    assert {r.valid_from for r in rows} == {DAY1}
    audited = await session.scalar(
        select(func.count()).where(AuditLog.entity_type == "client_report_types")
    )
    assert audited == 3
    # a doua recalculare nu mai schimbă nimic
    diff = (await service.plan(client, DAY1)).to_diff()
    assert diff.to_add == diff.to_deactivate == []
    assert codes(diff.unchanged) == ["EXTRASE", "IPC21", "TVA12"]


async def test_client_change_deactivates_auto(
    service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    client.has_employees = False
    diff = (await service.apply(client, DAY2)).to_diff()
    assert codes(diff.to_deactivate) == ["IPC21"]
    assert set(await active_codes(service, client)) == {"EXTRASE", "TVA12"}
    ipc = next(r for r in await service.list_obligations(client) if r.report_type.code == "IPC21")
    assert (ipc.is_active, ipc.valid_to) == (False, DAY2)


async def test_manual_assignment_is_kept(
    service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.assign_manual(
        client, ClientReportTypeCreate(report_type_id=classifier.id("TL13")), DAY1
    )
    diff = (await service.apply(client, DAY1)).to_diff()
    assert codes(diff.manual) == ["TL13"]
    assert "TL13" not in codes(diff.to_deactivate)
    assert (await active_codes(service, client))["TL13"] is ObligationSource.MANUAL


async def test_manual_deactivation_is_not_undone(
    service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    extrase = next(
        r for r in await service.list_obligations(client) if r.report_type.code == "EXTRASE"
    )
    row = await service.deactivate(extrase, DAY1)
    assert (row.is_active, row.source) == (False, ObligationSource.MANUAL)

    diff = (await service.apply(client, DAY2)).to_diff()
    assert codes(diff.manual_excluded) == ["EXTRASE"]
    assert "EXTRASE" not in codes(diff.to_add)
    assert "EXTRASE" not in await active_codes(service, client)


async def test_readd_on_same_day_reactivates_row(
    service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    client.has_employees = False
    await service.apply(client, DAY1)  # IPC21 dezactivat azi
    client.has_employees = True
    await service.apply(client, DAY1)  # și readăugat azi: fără conflict de unicitate
    rows = [r for r in await service.list_obligations(client) if r.report_type.code == "IPC21"]
    assert len(rows) == 1
    assert (rows[0].is_active, rows[0].valid_to) == (True, None)


async def test_retired_type_is_deactivated(
    session: AsyncSession, service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    tva = classifier.types["TVA12"]
    tva.valid_to, tva.is_active = date(2026, 9, 30), False
    await session.flush()
    diff = (await service.apply(client, DAY2)).to_diff()
    assert codes(diff.to_deactivate) == ["TVA12"]


async def test_apply_recomputes_instead_of_trusting_preview(
    service: MatrixService, client: Client, classifier: Classifier
) -> None:
    preview = (await service.plan(client, DAY1)).to_diff()
    assert "TVA12" in codes(preview.to_add)
    client.is_vat_payer = False  # se schimbă între previzualizare și aplicare
    applied = (await service.apply(client, DAY1)).to_diff()
    assert "TVA12" not in codes(applied.to_add)
    assert "TVA12" not in await active_codes(service, client)


async def test_assign_manual_errors(
    session: AsyncSession, service: MatrixService, client: Client, classifier: Classifier
) -> None:
    await service.apply(client, DAY1)
    with pytest.raises(ConflictError, match="TVA12"):
        await service.assign_manual(
            client, ClientReportTypeCreate(report_type_id=classifier.id("TVA12")), DAY1
        )
    with pytest.raises(ValidationFailedError, match="nu există"):
        await service.assign_manual(client, ClientReportTypeCreate(report_type_id=999_999), DAY1)
    tl13 = classifier.types["TL13"]
    tl13.is_active = False
    await session.flush()
    with pytest.raises(ValidationFailedError, match="retras"):
        await service.assign_manual(client, ClientReportTypeCreate(report_type_id=tl13.id), DAY1)


# --- Cine vede clientul ---


async def test_client_visibility(session: AsyncSession, client: Client, admin: User) -> None:
    director = await make_user(session, "director@birou.md", UserRole.DIRECTOR)
    ana = await make_user(session, "ana@birou.md", UserRole.CONTABIL)
    ion = await make_user(session, "ion@birou.md", UserRole.CONTABIL)
    await assign(session, client, ana)

    for user in (admin, director, ana):
        assert (await get_visible_client(session, user, client.id)).id == client.id
    with pytest.raises(NotFoundError):
        await get_visible_client(session, ion, client.id)
    with pytest.raises(NotFoundError):
        await get_visible_client(session, admin, 999_999)
