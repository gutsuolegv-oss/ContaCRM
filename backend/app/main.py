from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api import auth, classifiers, clients, grid, health, users
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ServiceError,
    ValidationFailedError,
)

_STATUS = {
    NotFoundError: status.HTTP_404_NOT_FOUND,
    ForbiddenError: status.HTTP_403_FORBIDDEN,
    ConflictError: status.HTTP_409_CONFLICT,
    ValidationFailedError: 422,
}


async def _service_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ServiceError)
    code = _STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
    return JSONResponse(status_code=code, content={"detail": exc.message})


def create_app() -> FastAPI:
    app = FastAPI(title="ContaCRM API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(classifiers.router)
    app.include_router(grid.router)
    app.include_router(clients.router)
    app.include_router(users.router)
    app.add_exception_handler(ServiceError, _service_error)
    return app


app = create_app()
