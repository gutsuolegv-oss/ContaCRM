"""Erori de domeniu. Rutele le transformă în coduri HTTP (404, 409, 422)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession


class ServiceError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    """Înregistrarea nu există sau utilizatorul nu are voie s-o vadă."""


class ForbiddenError(ServiceError):
    """Utilizatorul vede înregistrarea, dar nu are voie s-o modifice așa."""


class ConflictError(ServiceError):
    """Încalcă o regulă de unicitate sau înregistrarea e folosită în altă parte."""


class ValidationFailedError(ServiceError):
    """Datele sunt valide ca format, dar nu și în combinație cu ce e deja în bază."""


@asynccontextmanager
async def conflict_guard(session: AsyncSession, message: str) -> AsyncIterator[None]:
    """Modificările din bloc (add / setattr / delete) se scriu într-un savepoint. O constrângere
    încălcată devine ConflictError, savepoint-ul se anulează (cu tot cu obiectele adăugate în
    bloc), iar sesiunea rămâne utilizabilă. Modificările trebuie făcute ÎN bloc: un obiect
    adăugat înainte ar rămâne în sesiune și ar eșua din nou la următoarea scriere."""
    try:
        async with session.begin_nested():
            yield
            await session.flush()
    except IntegrityError as e:
        raise ConflictError(message) from e
