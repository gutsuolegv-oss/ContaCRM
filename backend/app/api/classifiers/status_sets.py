from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import ClassifierEditor, CurrentUser, SessionDep
from app.models import Status, StatusSet
from app.schemas.classifier import (
    StatusCreate,
    StatusOut,
    StatusSetCreate,
    StatusSetOut,
    StatusSetUpdate,
    StatusUpdate,
)
from app.services.classifier import ClassifierService

router = APIRouter(tags=["clasificator: statusuri"])


@router.get("/status-sets", response_model=list[StatusSetOut])
async def list_status_sets(session: SessionDep, user: CurrentUser) -> Sequence[StatusSet]:
    return await ClassifierService(session, user).list_status_sets()


@router.post("/status-sets", response_model=StatusSetOut, status_code=status.HTTP_201_CREATED)
async def create_status_set(
    body: StatusSetCreate, session: SessionDep, user: ClassifierEditor
) -> StatusSet:
    return await ClassifierService(session, user).create_status_set(body)


@router.patch("/status-sets/{set_id}", response_model=StatusSetOut)
async def update_status_set(
    set_id: int, body: StatusSetUpdate, session: SessionDep, user: ClassifierEditor
) -> StatusSet:
    return await ClassifierService(session, user).update_status_set(set_id, body)


@router.post(
    "/status-sets/{set_id}/statuses",
    response_model=StatusOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_status(
    set_id: int, body: StatusCreate, session: SessionDep, user: ClassifierEditor
) -> Status:
    return await ClassifierService(session, user).create_status(set_id, body)


@router.patch("/statuses/{status_id}", response_model=StatusOut)
async def update_status(
    status_id: int, body: StatusUpdate, session: SessionDep, user: ClassifierEditor
) -> Status:
    return await ClassifierService(session, user).update_status(status_id, body)


@router.delete("/statuses/{status_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_status(status_id: int, session: SessionDep, user: ClassifierEditor) -> None:
    await ClassifierService(session, user).delete_status(status_id)
