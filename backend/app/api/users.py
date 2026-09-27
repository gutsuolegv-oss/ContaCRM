"""/api/users — conturile utilizatorilor. Citire: admin și director; modificare: doar admin
(verificat în UserService)."""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, SessionDep, require_roles
from app.core.clock import utc_now
from app.models import User, UserRole
from app.schemas.users import PasswordReset, UserCreate, UserOut, UserUpdate
from app.services.users import UserService

router = APIRouter(prefix="/api/users", tags=["utilizatori"])

UserReader = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.DIRECTOR))]


@router.get("", response_model=list[UserOut])
async def list_users(
    session: SessionDep,
    user: UserReader,
    role: UserRole | None = None,
    include_archived: bool = False,
) -> Sequence[User]:
    return await UserService(session, user).list(role, include_archived)


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: SessionDep, user: UserReader) -> User:
    return await UserService(session, user).get(user_id)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, session: SessionDep, user: CurrentUser) -> User:
    """Cont nou cu parolă inițială; utilizatorul o schimbă la prima logare."""
    return await UserService(session, user).create(body)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdate, session: SessionDep, user: CurrentUser
) -> User:
    return await UserService(session, user).update(user_id, body)


@router.post("/{user_id}/reset-password", response_model=UserOut)
async def reset_password(
    user_id: int, body: PasswordReset, session: SessionDep, user: CurrentUser
) -> User:
    """Parolă nouă setată de admin; sesiunile utilizatorului se închid."""
    return await UserService(session, user).reset_password(user_id, body.password, utc_now())


@router.delete("/{user_id}", response_model=UserOut)
async def archive_user(user_id: int, session: SessionDep, user: CurrentUser) -> User:
    """Arhivare: nu se mai poate loga; repartizările lui la clienți se închid."""
    return await UserService(session, user).archive(user_id, utc_now())
