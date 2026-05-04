from __future__ import annotations

import pytest

from app.db import close_orm, init_orm
from app.db.models import User


@pytest.mark.asyncio
async def test_init_orm_can_auto_generate_schema(tmp_path) -> None:
    await init_orm(
        database_url=f"sqlite://{tmp_path / 'auto_schema.sqlite3'}",
        auto_generate_schema=True,
    )
    try:
        user = await User.create(
            username="schema-check",
            display_name="Schema Check",
            hashed_password="unused",
            is_test_user=True,
        )

        assert user.id > 0
    finally:
        await close_orm()
