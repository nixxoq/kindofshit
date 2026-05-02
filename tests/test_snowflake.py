from __future__ import annotations

from app.services.snowflake import SnowflakeGenerator


def test_snowflake_generator_is_monotonic_and_unique() -> None:
    generator = SnowflakeGenerator(worker_id=1)
    ids = [generator.next_id() for _ in range(256)]

    assert len(ids) == len(set(ids))
    assert ids == sorted(ids)
