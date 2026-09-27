from collections.abc import Sequence

from fastapi import APIRouter, status

from app.api.deps import ClassifierEditor, CurrentUser, SessionDep
from app.models import ReportCategory
from app.schemas.classifier import CategoryCreate, CategoryOut, CategoryUpdate
from app.services.classifier import ClassifierService

router = APIRouter(prefix="/categories", tags=["clasificator: categorii"])


@router.get("", response_model=list[CategoryOut])
async def list_categories(
    session: SessionDep, user: CurrentUser, active: bool | None = None
) -> Sequence[ReportCategory]:
    return await ClassifierService(session, user).list_categories(active)


@router.post("", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate, session: SessionDep, user: ClassifierEditor
) -> ReportCategory:
    return await ClassifierService(session, user).create_category(body)


@router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int, body: CategoryUpdate, session: SessionDep, user: ClassifierEditor
) -> ReportCategory:
    return await ClassifierService(session, user).update_category(category_id, body)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(category_id: int, session: SessionDep, user: ClassifierEditor) -> None:
    """Ștergere logică: is_active = false."""
    await ClassifierService(session, user).deactivate_category(category_id)
