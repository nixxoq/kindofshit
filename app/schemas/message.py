from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from typing import Optional


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)


class MessageResponse(BaseModel):
    id: int
    dm_id: int
    author_id: int
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None


class MessageHistoryResponse(BaseModel):
    items: list[MessageResponse]
    next_before: int | None

class EditMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4096)