from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Platform = Literal["windows", "android", "linux", "web", "unknown"]


class LoginAttemptCreate(BaseModel):
    device_id: str = Field(min_length=16, max_length=128)
    platform: Platform = "unknown"
    app_version: str | None = Field(default=None, min_length=1, max_length=32)


class LoginAttemptCreated(BaseModel):
    attempt_id: str
    poll_secret: str
    authorization_url: str
    expires_at: datetime
    poll_after_seconds: int = 2


class LoginAttemptStatus(BaseModel):
    attempt_id: str
    status: Literal["PENDING", "APPROVED", "EXPIRED", "FAILED", "EXCHANGED"]
    expires_at: datetime
    error_code: str | None = None


class LoginExchangeRequest(BaseModel):
    attempt_id: str = Field(min_length=36, max_length=36)
    poll_secret: str = Field(min_length=32, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=48, max_length=512)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: Literal["Bearer"] = "Bearer"
    access_expires_at: datetime
    refresh_expires_at: datetime
    session_id: str


class AuthSessionView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    device_id: str
    platform: str
    app_version: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool = False
