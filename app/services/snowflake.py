from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.config import get_settings


EPOCH_SNOWFLAKE = 1704067200000  # 2024-01-01T00:00:00Z
WORKER_ID_BITS = 10
SEQUENCE_BITS = 12
MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1


@dataclass
class SnowflakeGenerator:
    worker_id: int

    def __post_init__(self) -> None:
        if not 0 <= self.worker_id <= MAX_WORKER_ID:
            raise ValueError(f"worker_id must be between 0 and {MAX_WORKER_ID}")
        self._lock = threading.Lock()
        self._last_timestamp = -1
        self._sequence = 0

    def next_id(self) -> int:
        with self._lock:
            timestamp = self._current_millis()
            if timestamp < self._last_timestamp:
                timestamp = self._wait_for_next_millis(self._last_timestamp)

            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp = self._wait_for_next_millis(self._last_timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp
            return (
                ((timestamp - EPOCH_SNOWFLAKE) << (WORKER_ID_BITS + SEQUENCE_BITS))
                | (self.worker_id << SEQUENCE_BITS)
                | self._sequence
            )

    @staticmethod
    def _current_millis() -> int:
        return int(time.time() * 1000)

    def _wait_for_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            time.sleep(0.0001)
            timestamp = self._current_millis()
        return timestamp


_GENERATOR: SnowflakeGenerator | None = None


def get_generator() -> SnowflakeGenerator:
    global _GENERATOR
    if not _GENERATOR:
        _GENERATOR = SnowflakeGenerator(worker_id=get_settings().snowflake_worker_id)
    return _GENERATOR


def generate_snowflake() -> int:
    return get_generator().next_id()
