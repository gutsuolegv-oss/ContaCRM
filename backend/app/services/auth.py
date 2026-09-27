"""Autentificare: login, reîmprospătarea sesiunii (rotirea refresh token-ului), logout."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.repositories.refresh_token import RefreshTokenRepository
from app.repositories.user import UserRepository


class AuthError(Exception):
    """Date de autentificare greșite. Mesajul nu spune care anume, intenționat."""


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    expires_in: int


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = RefreshTokenRepository(session)

    async def login(self, email: str, password: str) -> TokenPair:
        user = await self.users.get_active_by_email(email)
        if user is None:
            security.verify_password(security.dummy_password_hash(), password)
            raise AuthError
        if not security.verify_password(user.password_hash, password):
            raise AuthError

        now = datetime.now(UTC)
        if security.password_needs_rehash(user.password_hash):
            user.password_hash = security.hash_password(password)
        user.last_login_at = now
        pair = self._issue(user.id, now)
        await self.session.commit()
        return pair

    async def refresh(self, raw_token: str) -> TokenPair:
        now = datetime.now(UTC)
        token = await self.tokens.get_by_hash_for_update(security.hash_token(raw_token))
        if token is None:
            raise AuthError
        if token.revoked_at is not None:
            # Un token deja folosit apare din nou: probabil a fost furat.
            # Se închid toate sesiunile utilizatorului.
            await self.tokens.revoke_all_for_user(token.user_id, now)
            await self.session.commit()
            raise AuthError
        if token.expires_at <= now or await self.users.get_active(token.user_id) is None:
            raise AuthError

        token.revoked_at = now
        pair = self._issue(token.user_id, now)
        await self.session.commit()
        return pair

    async def logout(self, raw_token: str) -> None:
        token = await self.tokens.get_by_hash_for_update(security.hash_token(raw_token))
        if token is not None and token.revoked_at is None:
            token.revoked_at = datetime.now(UTC)
            await self.session.commit()

    def _issue(self, user_id: int, now: datetime) -> TokenPair:
        settings = get_settings()
        raw = security.new_refresh_token()
        self.tokens.add(
            user_id,
            security.hash_token(raw),
            now + timedelta(days=settings.refresh_token_ttl_days),
        )
        return TokenPair(
            access_token=security.create_access_token(user_id, now),
            refresh_token=raw,
            expires_in=settings.access_token_ttl_minutes * 60,
        )
