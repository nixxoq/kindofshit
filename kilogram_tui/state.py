from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from kilogram_tui.models import SessionState

STATE_ENV = "KILOGRAM_TUI_STATE"
DEFAULT_STATE_PATH = Path.home() / ".kilogram_tui.json"


def state_path() -> Path:
    override = os.getenv(STATE_ENV)
    return Path(override).expanduser() if override else DEFAULT_STATE_PATH


def load_session(path: Path | None = None) -> SessionState | None:
    target = path or state_path()
    if not target.exists():
        return None

    try:
        data: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
        return SessionState(
            base_url=str(data["base_url"]),
            token=str(data["token"]),
            user_id=int(data["user_id"]),
            username=str(data["username"]),
            hidden_dm_ids=frozenset(
                int(dm_id) for dm_id in data.get("hidden_dm_ids", [])
            ),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def save_session(session: SessionState, path: Path | None = None) -> None:
    target = path or state_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "base_url": session.base_url,
        "token": session.token,
        "user_id": session.user_id,
        "username": session.username,
        "hidden_dm_ids": sorted(session.hidden_dm_ids),
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def clear_session(path: Path | None = None) -> None:
    target = path or state_path()
    try:
        target.unlink()
    except FileNotFoundError:
        return
