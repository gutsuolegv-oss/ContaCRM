from fastapi import FastAPI

from app.api import auth, health


def create_app() -> FastAPI:
    app = FastAPI(title="ContaCRM API", version="0.1.0")
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
