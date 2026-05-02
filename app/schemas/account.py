from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AccountCreationRequest(BaseModel):  # form
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=20)


class AccountResponse(BaseModel):
    id: int
    created_at: datetime
    token: str

class LoginPayload(BaseModel): # form
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=20)    
    
class LoginResponse(BaseModel):
    user_id: int
    username: str
    token: str