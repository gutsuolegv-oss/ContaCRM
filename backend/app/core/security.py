"""Parole (Argon2) și token-uri.

- Access token: JWT semnat cu APP_SECRET_KEY, valabil câteva minute. Nu se salvează în bază.
- Refresh token: șir aleatoriu opac; în bază se salvează doar hash-ul SHA-256.
"""

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def dummy_password_hash() -> str:
    """Hash verificat când emailul nu există, ca răspunsul să dureze la fel ca la o parolă
    greșită (altfel timpul de răspuns ar arăta ce conturi există)."""
    return _hasher.hash(secrets.token_urlsafe(16))


def create_access_token(user_id: int, now: datetime, session_version: int = 0) -> str:
    ttl = timedelta(minutes=get_settings().access_token_ttl_minutes)
    payload = {
        "sub": str(user_id),
        "type": "access",
        "sv": session_version,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, get_settings().app_secret_key.get_secret_value(), _ALGORITHM)


@dataclass(frozen=True)
class AccessClaims:
    user_id: int
    session_version: int


def decode_access_token(token: str) -> AccessClaims | None:
    """Datele tokenului, sau None dacă e invalid, expirat sau nu e access token."""
    try:
        payload = jwt.decode(
            token,
            get_settings().app_secret_key.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={"require": ["sub", "exp", "type", "sv"]},
        )
    except jwt.PyJWTError:
        return None
    if payload["type"] != "access":
        return None
    try:
        return AccessClaims(int(payload["sub"]), int(payload["sv"]))
    except (TypeError, ValueError):
        return None


def new_refresh_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
