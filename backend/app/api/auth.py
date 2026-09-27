from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, SessionDep
from app.models import User
from app.schemas.auth import LoginIn, RefreshIn, TokenPairOut, UserOut
from app.services.auth import AuthError, AuthService, TokenPair

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _out(pair: TokenPair) -> TokenPairOut:
    return TokenPairOut(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        expires_in=pair.expires_in,
    )


@router.post("/login", response_model=TokenPairOut)
async def login(body: LoginIn, session: SessionDep) -> TokenPairOut:
    try:
        return _out(await AuthService(session).login(body.email, body.password))
    except AuthError:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, detail="Email sau parolă greșită"
        ) from None


@router.post("/refresh", response_model=TokenPairOut)
async def refresh(body: RefreshIn, session: SessionDep) -> TokenPairOut:
    try:
        return _out(await AuthService(session).refresh(body.refresh_token))
    except AuthError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Sesiune expirată") from None


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshIn, session: SessionDep) -> None:
    await AuthService(session).logout(body.refresh_token)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
