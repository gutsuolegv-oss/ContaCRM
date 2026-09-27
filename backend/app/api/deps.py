"""Dependențe comune pentru rute: sesiunea DB, utilizatorul curent, verificarea rolului."""

from collections.abc import Awaitable, Callable
from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.clock import local_today
from app.core.security import decode_access_token
from app.db.session import get_session
from app.models import User, UserRole
from app.repositories.user import UserRepository

SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False)

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Neautentificat",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Utilizatorul din access token. Se citește din bază la fiecare cerere, ca un cont
    arhivat sau un rol schimbat să aibă efect imediat, nu abia la expirarea tokenului."""
    if credentials is None:
        raise _UNAUTHORIZED
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise _UNAUTHORIZED
    user = await UserRepository(session).get_active(user_id)
    if user is None:
        raise _UNAUTHORIZED
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[[User], Awaitable[User]]:
    """Dependență: `user: Annotated[User, Depends(require_roles(UserRole.ADMIN))]`."""

    async def _check(user: CurrentUser) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Acces interzis")
        return user

    return _check


# Cine poate modifica clasificatorul de rapoarte și obligațiile clienților.
ClassifierEditor = Annotated[User, Depends(require_roles(UserRole.ADMIN, UserRole.DIRECTOR))]


async def get_today() -> date:
    """„Azi” pentru termene și întârzieri. Dependență, ca testele s-o poată fixa."""
    return local_today()


Today = Annotated[date, Depends(get_today)]
