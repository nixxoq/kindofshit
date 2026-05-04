from __future__ import annotations

from tortoise import Tortoise

from app.config import get_settings


def build_tortoise_config(database_url: str | None = None) -> dict:
    settings = get_settings()
    return {
        "connections": {"default": database_url or settings.database_url},
        "apps": {
            "models": {
                "models": ["app.db.models"],
                "default_connection": "default",
                "migrations": "app.db.migrations",
            }
        },
        "use_tz": True,
        "timezone": "UTC",
    }


TORTOISE_ORM = build_tortoise_config()


async def init_orm(
    database_url: str | None = None,
    auto_generate_schema: bool = False,
) -> None:
    await Tortoise.init(
        config=build_tortoise_config(database_url=database_url),
        _enable_global_fallback=True,
    )
    if auto_generate_schema:
        await Tortoise.generate_schemas(safe=True)


async def close_orm() -> None:
    await Tortoise.close_connections()


# TODO: move database healthcheck after migrating to docker
async def healthcheck() -> bool:
    connection = Tortoise.get_connection("default")
    await connection.execute_query("SELECT 1")
    return True
