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

PASSWORD_CHANGE_REQUIRED = "Schimbă parola setată de administrator înainte de a continua"  # noqa: S105

_UNAUTHORIZED = HTTPException(
    status.HTTP_401_UNAUTHORIZED,
    detail="Neautentificat",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_user_even_if_password_change_required(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    """Utilizatorul din access token. Se citește din bază la fiecare cerere, ca un cont
    arhivat sau un rol schimbat să aibă efect imediat, nu abia la expirarea tokenului.
    Tokenurile emise înainte de o schimbare de parolă (versiune de sesiune veche) sunt
    refuzate."""
    if credentials is None:
        raise _UNAUTHORIZED
    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise _UNAUTHORIZED
    user = await UserRepository(session).get_active(claims.user_id)
    if user is None or claims.session_version != user.session_version:
        raise _UNAUTHORIZED
    return user


async def get_current_user(
    user: Annotated[User, Depends(get_user_even_if_password_change_required)],
) -> User:
    """Ca mai sus, dar refuză orice acțiune până când utilizatorul își schimbă parola
    setată de admin (în afară de /api/auth/me și /api/auth/change-password)."""
    if user.must_change_password:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=PASSWORD_CHANGE_REQUIRED)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
# Doar pentru /api/auth/me și /api/auth/change-password.
UserPendingPasswordChange = Annotated[User, Depends(get_user_even_if_password_change_required)]


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
