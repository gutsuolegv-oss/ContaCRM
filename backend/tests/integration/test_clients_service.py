from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import RecordStatus
from app.models import AuditLog, Client, ClientStatus, LegalForm, User, UserRole
from app.schemas.classifier import ReportTypeBrief
from app.schemas.clients import (
    BankAccountCreate,
    BankAccountUpdate,
    ClientCreate,
    ClientUpdate,
    ContactCreate,
    ContactUpdate,
)
from app.schemas.matrix import RecalculateDiff
from app.seed.classifier import seed_classifier
from app.services.clients import ClientService, client_list_item, client_out
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationFailedError,
)
from tests.integration.factories import make_user

TODAY = date(2026, 9, 27)
NOW = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
IBAN_1 = "MD24AG000000022512345678"
IBAN_2 = "MD68VI000000022512345679"


class Users:
    admin: User
    ana: User
    ion: User


@pytest.fixture
async def users(session: AsyncSession) -> Users:
    await seed_classifier(session)
    u = Users()
    u.admin = await make_user(session, "admin", UserRole.ADMIN)
    u.ana = await make_user(session, "ana", UserRole.CONTABIL)
    u.ion = await make_user(session, "ion", UserRole.CONTABIL)
    return u


def svc(session: AsyncSession, user: User) -> ClientService:
    return ClientService(session, user)


def new_client(idno: str = "1003600012345", **kw: object) -> ClientCreate:
    fields: dict[str, object] = {"name": "Agro-Nord SRL", "idno": idno, "legal_form": "SRL"}
    fields.update(kw)
    return ClientCreate.model_validate(fields)


async def create_for_ana(
    session: AsyncSession, users: Users, data: ClientCreate
) -> tuple[Client, RecalculateDiff]:
    """Adminul adaugă clientul și i-l repartizează Anei (contabilul nu adaugă clienți)."""
    admin = svc(session, users.admin)
    client, diff = await admin.create(data, TODAY)
    await admin.assign(client.id, users.ana.id)
    return await svc(session, users.ana).get_card(client.id), diff


def codes(briefs: list[ReportTypeBrief]) -> list[str]:
    return sorted(b.code for b in briefs)


# --- Creare ---


async def test_accountant_cannot_create_client(session: AsyncSession, users: Users) -> None:
    with pytest.raises(ForbiddenError):
        await svc(session, users.ana).create(new_client(), TODAY)


async def test_new_client_onboarding(session: AsyncSession, users: Users) -> None:
    client, diff = await create_for_ana(session, users, new_client(is_vat_payer=True))
    out = client_out(client)
    assert out.client_status is ClientStatus.ONBOARDING
    assert [a.id for a in out.accountants] == [users.ana.id]
    assert codes(diff.to_add) == ["EXTRASE", "FACT_LIVR", "FACT_PROC", "TVA12"]
    assert diff.as_of == TODAY
    created = (
        await session.scalars(select(AuditLog).where(AuditLog.entity_type == "clients"))
    ).one()
    assert created.user_id == users.admin.id


async def test_admin_created_client_has_no_accountant(session: AsyncSession, users: Users) -> None:
    client, _ = await svc(session, users.admin).create(new_client(), TODAY)
    assert client_out(client).accountants == []


async def test_idno_unique_until_archived(session: AsyncSession, users: Users) -> None:
    admin = svc(session, users.admin)
    client, _ = await admin.create(new_client(), TODAY)
    with pytest.raises(ConflictError, match="IDNO"):
        await admin.create(new_client(name="Dublură"), TODAY)
    await admin.archive(client.id, NOW)
    await admin.create(new_client(name="Agro-Nord (nou)"), TODAY)


# --- Modificare și recalculare ---


async def test_rule_field_change_recalculates(session: AsyncSession, users: Users) -> None:
    ana = svc(session, users.ana)
    client, _ = await create_for_ana(session, users, new_client())
    _, diff = await ana.update(client.id, ClientUpdate(has_employees=True), TODAY)
    assert diff is not None and codes(diff.to_add) == ["IPC21"]
    _, diff = await ana.update(client.id, ClientUpdate(notes="client din 2023"), TODAY)
    assert diff is None
    _, diff = await ana.update(client.id, ClientUpdate(legal_form=LegalForm.SA), TODAY)
    assert diff is not None and diff.to_add == diff.to_deactivate == []  # nicio regulă pe formă


async def test_vat_code_follows_vat_status(session: AsyncSession, users: Users) -> None:
    ana = svc(session, users.ana)
    client, _ = await create_for_ana(
        session, users, new_client(is_vat_payer=True, vat_code="0600012")
    )
    with pytest.raises(ValidationFailedError, match="vat_code"):
        await ana.update(client.id, ClientUpdate(is_vat_payer=False, vat_code="0600013"), TODAY)
    client, diff = await ana.update(client.id, ClientUpdate(is_vat_payer=False), TODAY)
    assert client.vat_code is None
    assert diff is not None and codes(diff.to_deactivate) == ["TVA12"]


async def test_only_editors_change_client_status(session: AsyncSession, users: Users) -> None:
    client, _ = await create_for_ana(session, users, new_client())
    activate = ClientUpdate(client_status=ClientStatus.ACTIVE)
    with pytest.raises(ForbiddenError):
        await svc(session, users.ana).update(client.id, activate, TODAY)
    client, _ = await svc(session, users.admin).update(client.id, activate, TODAY)
    assert client.client_status is ClientStatus.ACTIVE


async def test_other_accountant_cannot_see(session: AsyncSession, users: Users) -> None:
    client, _ = await create_for_ana(session, users, new_client())
    ion = svc(session, users.ion)
    with pytest.raises(NotFoundError):
        await ion.get_card(client.id)
    with pytest.raises(NotFoundError):
        await ion.update(client.id, ClientUpdate(notes="x"), TODAY)


async def test_null_on_required_field(session: AsyncSession, users: Users) -> None:
    client, _ = await svc(session, users.admin).create(new_client(), TODAY)
    with pytest.raises(ValidationFailedError, match="name"):
        await svc(session, users.admin).update(client.id, ClientUpdate(name=None), TODAY)


# --- Arhivare și căutare ---


async def test_archive(session: AsyncSession, users: Users) -> None:
    client, _ = await create_for_ana(session, users, new_client())
    with pytest.raises(ForbiddenError):
        await svc(session, users.ana).archive(client.id, NOW)
    await svc(session, users.admin).archive(client.id, NOW)
    card = await svc(session, users.admin).get_card(client.id)
    assert (card.status, card.deleted_by) == (RecordStatus.ARCHIVED, users.admin.id)
    with pytest.raises(NotFoundError):
        await svc(session, users.ana).get_card(client.id)
    with pytest.raises(NotFoundError):
        await svc(session, users.admin).update(client.id, ClientUpdate(notes="x"), TODAY)


async def test_search(session: AsyncSession, users: Users) -> None:
    ana, admin = svc(session, users.ana), svc(session, users.admin)
    await create_for_ana(
        session, users, new_client("1003600012345", name="Agro-Nord SRL", is_vat_payer=True)
    )
    await admin.create(new_client("1002600054321", name="Vinăria Codru SA"), TODAY)
    gone, _ = await admin.create(new_client("1010600023456", name="ÎI Moraru Petru"), TODAY)
    await admin.archive(gone.id, NOW)

    total, items = await admin.search(q="agro")
    assert (total, [c.name for c in items]) == (1, ["Agro-Nord SRL"])
    assert [c.idno for c in (await admin.search(q="100260"))[1]] == ["1002600054321"]
    assert (await admin.search())[0] == 2
    assert (await admin.search(include_archived=True))[0] == 3
    assert [c.name for c in (await admin.search(is_vat_payer=True))[1]] == ["Agro-Nord SRL"]
    assert (await admin.search(assigned_user_id=users.ana.id))[0] == 1
    total, page = await admin.search(limit=1, offset=1)
    assert (total, [c.name for c in page]) == (2, ["Vinăria Codru SA"])
    # „%” se caută literal, nu ca wildcard
    assert (await admin.search(q="%"))[0] == 0

    total, items = await ana.search(include_archived=True)
    assert [c.name for c in items] == ["Agro-Nord SRL"]
    assert [a.id for a in client_list_item(items[0]).accountants] == [users.ana.id]


# --- Conturi bancare și contacte ---


async def test_bank_accounts(session: AsyncSession, users: Users) -> None:
    ana = svc(session, users.ana)
    client, _ = await create_for_ana(session, users, new_client())
    card = await ana.add_bank_account(
        client.id, BankAccountCreate(bank_name="MAIB", iban=IBAN_1, is_primary=True)
    )
    card = await ana.add_bank_account(
        client.id,
        BankAccountCreate(bank_name="Victoriabank", iban=IBAN_2, currency="eur", is_primary=True),
    )
    out = client_out(card)
    assert [(a.bank_name, a.is_primary, a.currency) for a in out.bank_accounts] == [
        ("Victoriabank", True, "EUR"),
        ("MAIB", False, "MDL"),
    ]
    with pytest.raises(ConflictError, match="IBAN"):
        await ana.add_bank_account(client.id, BankAccountCreate(bank_name="X", iban=IBAN_1))

    maib = next(a for a in out.bank_accounts if a.bank_name == "MAIB")
    card = await ana.update_bank_account(maib.id, BankAccountUpdate(is_primary=True))
    assert [a.bank_name for a in client_out(card).bank_accounts if a.is_primary] == ["MAIB"]
    card = await ana.delete_bank_account(maib.id, NOW)
    assert [a.bank_name for a in client_out(card).bank_accounts] == ["Victoriabank"]
    with pytest.raises(NotFoundError):
        await svc(session, users.ion).update_bank_account(
            client_out(card).bank_accounts[0].id, BankAccountUpdate(bank_name="Y")
        )


async def test_contacts(session: AsyncSession, users: Users) -> None:
    ana = svc(session, users.ana)
    client, _ = await create_for_ana(session, users, new_client())
    await ana.add_contact(
        client.id,
        ContactCreate(full_name="Petru Moraru", position="Administrator", is_primary=True),
    )
    card = await ana.add_contact(client.id, ContactCreate(full_name="Natalia Ursu"))
    natalia = next(c for c in client_out(card).contacts if c.full_name == "Natalia Ursu")
    card = await ana.update_contact(natalia.id, ContactUpdate(is_primary=True, phone="+37369"))
    contacts = client_out(card).contacts
    assert [(c.full_name, c.is_primary) for c in contacts] == [
        ("Natalia Ursu", True),
        ("Petru Moraru", False),
    ]
    card = await ana.delete_contact(natalia.id, NOW)
    assert [c.full_name for c in client_out(card).contacts] == ["Petru Moraru"]


# --- Repartizări ---


async def test_assignments(session: AsyncSession, users: Users) -> None:
    client, _ = await create_for_ana(session, users, new_client())
    admin = svc(session, users.admin)
    with pytest.raises(ForbiddenError):
        await svc(session, users.ana).assign(client.id, users.ion.id)
    history = await admin.assign(client.id, users.ion.id)
    assert {a.user_id for a in history} == {users.ana.id, users.ion.id}
    with pytest.raises(ConflictError):
        await admin.assign(client.id, users.ion.id)
    with pytest.raises(ValidationFailedError):
        await admin.assign(client.id, 999_999)

    card = await svc(session, users.ion).get_card(client.id)
    assert {a.id for a in client_out(card).accountants} == {users.ana.id, users.ion.id}

    ana_assignment = next(a for a in history if a.user_id == users.ana.id)
    now = datetime.now(UTC)  # după assigned_at, pus de bază la ora reală
    history = await admin.unassign(ana_assignment.id, now)
    closed = next(a for a in history if a.id == ana_assignment.id)
    assert (closed.unassigned_at, closed.unassigned_by) == (now, users.admin.id)
    with pytest.raises(NotFoundError):
        await svc(session, users.ana).get_card(client.id)
    # istoricul rămâne vizibil pentru cine vede clientul
    assert len(await svc(session, users.ion).assignment_history(client.id)) == 2
