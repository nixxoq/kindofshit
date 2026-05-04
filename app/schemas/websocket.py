from __future__ import annotations

from typing import Any

from pydantic import BaseModel

# TODO: add more events (message created, edited, removed, pinned, unpinned, etc.)


class ReadyEventData(BaseModel):
    user_id: int


class ErrorEventData(BaseModel):
    detail: str


class WebSocketEvent(BaseModel):
    type: str
    data: dict[str, Any]
