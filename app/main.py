from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import rest_router, ws_router
from app.config import Settings, get_settings, reset_settings_cache
from app.db import close_orm, init_orm
from app.services.websocket import connection_manager


def create_app(settings: Settings | None = None) -> FastAPI:
    base_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        worker_id = (os.getpid() % 31) + 1
        os.environ["SNOWFLAKE_WORKER_ID"] = str(worker_id)
        reset_settings_cache()

        current_settings = get_settings()

        await init_orm(
            database_url=current_settings.database_url,
            auto_generate_schema=current_settings.auto_generate_schema,
        )
        await connection_manager.setup()
        try:
            yield
        finally:
            await connection_manager.teardown()
            await close_orm()

    app = FastAPI(
        title=base_settings.app_name,
        debug=base_settings.debug,
        lifespan=lifespan,
    )
    app.include_router(rest_router)
    app.include_router(ws_router)
    return app


app = create_app()
