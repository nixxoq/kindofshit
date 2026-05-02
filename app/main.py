from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import rest_router, ws_router
from app.config import Settings, get_settings
from app.db import close_orm, init_orm


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await init_orm(database_url=app_settings.database_url)
        try:
            yield
        finally:
            await close_orm()

    app = FastAPI(
        title=app_settings.app_name,
        debug=app_settings.debug,
        lifespan=lifespan,
    )
    app.include_router(rest_router)
    app.include_router(ws_router)
    return app


app = create_app()
