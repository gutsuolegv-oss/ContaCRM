"""/api/clients — cartela clientului, conturi bancare, contacte, contabili repartizați.

Contabilul vede și modifică doar clienții repartizați lui. Adăugarea, arhivarea, repartizările
și `client_status`: admin și director.
Permisiunile le verifică serviciul (ClientService).
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUser, SessionDep, Today
from app.core.clock import utc_now
from app.models import ClientAssignment, ClientStatus
from app.schemas.clients import (
    AssignmentCreate,
    AssignmentOut,
    BankAccountCreate,
    BankAccountUpdate,
    ClientCreate,
    ClientListOut,
    ClientOut,
    ClientSaveOut,
    ClientUpdate,
    ContactCreate,
    ContactUpdate,
)
from app.services.clients import ClientService, client_list_item, client_out

router = APIRouter(tags=["clienți"])


@router.get("/api/clients", response_model=ClientListOut)
async def list_clients(
    session: SessionDep,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    client_status: ClientStatus | None = None,
    is_vat_payer: bool | None = None,
    assigned_user_id: int | None = None,
    include_archived: bool = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClientListOut:
    """`q`: denumire (oriunde în text) sau IDNO (de la început). Arhivații: doar admin/director."""
    total, clients = await ClientService(session, user).search(
        q=q,
        client_status=client_status,
        is_vat_payer=is_vat_payer,
        assigned_user_id=assigned_user_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return ClientListOut(total=total, items=[client_list_item(c) for c in clients])


@router.post("/api/clients", response_model=ClientSaveOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    body: ClientCreate, session: SessionDep, user: CurrentUser, today: Today
) -> ClientSaveOut:
    """Doar admin și director. Clientul pornește în `onboarding`, fără contabil; obligațiile
    se calculează automat de azi."""
    client, diff = await ClientService(session, user).create(body, today)
    return ClientSaveOut(client=client_out(client), recalculation=diff)


@router.get("/api/clients/{client_id}", response_model=ClientOut)
async def get_client(client_id: int, session: SessionDep, user: CurrentUser) -> ClientOut:
    return client_out(await ClientService(session, user).get_card(client_id))


@router.patch("/api/clients/{client_id}", response_model=ClientSaveOut)
async def update_client(
    client_id: int, body: ClientUpdate, session: SessionDep, user: CurrentUser, today: Today
) -> ClientSaveOut:
    """Dacă se schimbă un atribut folosit de reguli, obligațiile se recalculează automat și
    `recalculation` arată ce s-a schimbat."""
    client, diff = await ClientService(session, user).update(client_id, body, today)
    return ClientSaveOut(client=client_out(client), recalculation=diff)


@router.delete("/api/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_client(client_id: int, session: SessionDep, user: CurrentUser) -> None:
    """Arhivare (ștergere logică). Doar admin și director."""
    await ClientService(session, user).archive(client_id, utc_now())


# --- Conturi bancare ---


@router.post(
    "/api/clients/{client_id}/bank-accounts",
    response_model=ClientOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_bank_account(
    client_id: int, body: BankAccountCreate, session: SessionDep, user: CurrentUser
) -> ClientOut:
    return client_out(await ClientService(session, user).add_bank_account(client_id, body))


@router.patch("/api/bank-accounts/{account_id}", response_model=ClientOut)
async def update_bank_account(
    account_id: int, body: BankAccountUpdate, session: SessionDep, user: CurrentUser
) -> ClientOut:
    return client_out(await ClientService(session, user).update_bank_account(account_id, body))


@router.delete("/api/bank-accounts/{account_id}", response_model=ClientOut)
async def delete_bank_account(account_id: int, session: SessionDep, user: CurrentUser) -> ClientOut:
    return client_out(await ClientService(session, user).delete_bank_account(account_id, utc_now()))


# --- Contacte ---


@router.post(
    "/api/clients/{client_id}/contacts",
    response_model=ClientOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_contact(
    client_id: int, body: ContactCreate, session: SessionDep, user: CurrentUser
) -> ClientOut:
    return client_out(await ClientService(session, user).add_contact(client_id, body))


@router.patch("/api/contacts/{contact_id}", response_model=ClientOut)
async def update_contact(
    contact_id: int, body: ContactUpdate, session: SessionDep, user: CurrentUser
) -> ClientOut:
    return client_out(await ClientService(session, user).update_contact(contact_id, body))


@router.delete("/api/contacts/{contact_id}", response_model=ClientOut)
async def delete_contact(contact_id: int, session: SessionDep, user: CurrentUser) -> ClientOut:
    return client_out(await ClientService(session, user).delete_contact(contact_id, utc_now()))


# --- Repartizări ---


@router.get("/api/clients/{client_id}/assignments", response_model=list[AssignmentOut])
async def assignment_history(
    client_id: int, session: SessionDep, user: CurrentUser
) -> Sequence[ClientAssignment]:
    """Contabilii clientului, inclusiv cei scoși (istoric), cei mai recenți primii."""
    return await ClientService(session, user).assignment_history(client_id)


@router.post(
    "/api/clients/{client_id}/assignments",
    response_model=list[AssignmentOut],
    status_code=status.HTTP_201_CREATED,
)
async def assign(
    client_id: int, body: AssignmentCreate, session: SessionDep, user: CurrentUser
) -> Sequence[ClientAssignment]:
    return await ClientService(session, user).assign(client_id, body.user_id)


@router.delete("/api/client-assignments/{assignment_id}", response_model=list[AssignmentOut])
async def unassign(
    assignment_id: int, session: SessionDep, user: CurrentUser
) -> Sequence[ClientAssignment]:
    """Închide repartizarea (unassigned_at); rândul rămâne ca istoric."""
    return await ClientService(session, user).unassign(assignment_id, utc_now())
