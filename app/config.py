from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from functools import lru_cache

# fixme: obsolete?
def _as_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    app_name: str
    debug: bool
    database_url: str
    secret_key: str
    auth_token_secret: str
    auto_generate_schema: bool
    snowflake_worker_id: int
    message_history_default_limit: int
    message_history_max_limit: int

    @property
    def encryption_key_bytes(self) -> bytes:
        return decode_base64_key(self.secret_key)

    @property
    def auth_secret_bytes(self) -> bytes:
        return decode_base64_key(self.auth_token_secret)


def decode_base64_key(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8"))
    except Exception as exc:
        raise ValueError("SECRET_KEY must be valid base64") from exc

    if len(decoded) not in {16, 24, 32}:
        raise ValueError("SECRET_KEY must decode to 16, 24, or 32 bytes")
    return decoded


def _dev_key(material: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(material.encode("utf-8")).digest()).decode(
        "utf-8"
    )


# TODO: move this into .env file
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    debug = _as_bool(os.getenv("DEBUG"), True)
    secret_key = os.getenv("SECRET_KEY", _dev_key("kilogram-dev-message-key"))
    auth_token_secret = os.getenv("AUTH_TOKEN_SECRET", secret_key)

    return Settings(
        app_name=os.getenv("APP_NAME", "Kilogram"),
        debug=debug,
        database_url=os.getenv(
            "DATABASE_URL",
            "postgres://kilogram:kilogram@127.0.0.1:5432/kilogram",
        ),
        secret_key=secret_key,
        auth_token_secret=auth_token_secret,
        auto_generate_schema=_as_bool(os.getenv("AUTO_GENERATE_SCHEMA"), False),
        snowflake_worker_id=int(os.getenv("SNOWFLAKE_WORKER_ID", "1")),
        message_history_default_limit=int(os.getenv("MESSAGE_HISTORY_DEFAULT_LIMIT", "50")),
        message_history_max_limit=int(os.getenv("MESSAGE_HISTORY_MAX_LIMIT", "100")),
    )


def reset_settings_cache() -> None:
    get_settings.cache_clear()
