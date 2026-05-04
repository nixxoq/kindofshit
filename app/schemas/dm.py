from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.account import UserPublicResponse


class OpenDMRequest(BaseModel):
    recipient_id: int = Field(gt=0)


class DMResponse(BaseModel):
    id: int
    peer_user_id: int
    peer: UserPublicResponse
    created_at: datetime
