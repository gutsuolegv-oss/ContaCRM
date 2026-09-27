"""/api/auth — login, sesiune, parolă.

Access token-ul (15 min) se întoarce în JSON și se trimite în antetul Authorization.
Refresh token-ul (30 de zile) stă într-un cookie httpOnly, Secure, SameSite=Strict, trimis
de browser doar la /api/auth/*: JavaScript-ul paginii nu îl poate citi, iar alte site-uri nu îl
pot folosi (CSRF).
"""

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.api.deps import SessionDep, UserPendingPasswordChange
from app.core.clock import utc_now
from app.core.config import get_settings
from app.models import User
from app.schemas.auth import AccessTokenOut, LoginIn, MeOut
from app.schemas.users import PasswordChange
from app.services.auth import AuthError, AuthService, TokenPair
from app.services.users import UserService

router = APIRouter(prefix="/api/auth", tags=["auth"])

REFRESH_COOKIE = "contacrm_refresh"
_COOKIE_PATH = "/api/auth"

RefreshCookie = Annotated[str | None, Cookie(alias=REFRESH_COOKIE, max_length=255)]


def _session(response: Response, pair: TokenPair) -> AccessTokenOut:
    """Pune refresh token-ul în cookie și întoarce access token-ul."""
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        pair.refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 3600,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )
    return AccessTokenOut(access_token=pair.access_token, expires_in=pair.expires_in)


def _clear(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        REFRESH_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
    )


@router.post("/login", response_model=AccessTokenOut)
async def login(body: LoginIn, response: Response, session: SessionDep) -> AccessTokenOut:
    try:
        return _session(response, await AuthService(session).login(body.email, body.password))
    except AuthError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Email sau parolă greșită"
        ) from None


@router.post("/refresh", response_model=AccessTokenOut)
async def refresh(
    response: Response, session: SessionDep, refresh_token: RefreshCookie = None
) -> AccessTokenOut:
    """Access token nou (și refresh token nou în cookie; cel vechi nu mai merge)."""
    expired = HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesiune expirată")
    if not refresh_token:
        raise expired
    try:
        return _session(response, await AuthService(session).refresh(refresh_token))
    except AuthError:
        raise expired from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response, session: SessionDep, refresh_token: RefreshCookie = None
) -> None:
    if refresh_token:
        await AuthService(session).logout(refresh_token)
    _clear(response)


@router.get("/me", response_model=MeOut)
async def me(user: UserPendingPasswordChange) -> User:
    """Merge și când parola trebuie schimbată (`must_change_password`)."""
    return user


@router.post("/change-password", response_model=AccessTokenOut)
async def change_password(
    body: PasswordChange,
    response: Response,
    session: SessionDep,
    user: UserPendingPasswordChange,
) -> AccessTokenOut:
    """Închide toate sesiunile, inclusiv pe alte dispozitive, și întoarce o sesiune nouă."""
    pair = await UserService(session, user).change_own_password(body, utc_now())
    return _session(response, pair)
