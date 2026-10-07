from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class RegisterIn(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=80)
    password: str = Field(min_length=10, max_length=128)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr
    display_name: str
    role: Literal["user", "organizer", "admin"]


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChallengeIn(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=10, max_length=2000)
    sport: str = Field(min_length=2, max_length=50)
    unit: str = Field(min_length=1, max_length=30)
    target_value: int = Field(gt=0, le=1_000_000)
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def valid_period(self):
        if self.starts_at.tzinfo is None or self.ends_at.tzinfo is None:
            raise ValueError("Dates must contain a timezone")
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class ChallengePatch(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=120)
    description: str | None = Field(default=None, min_length=10, max_length=2000)
    sport: str | None = Field(default=None, min_length=2, max_length=50)
    unit: str | None = Field(default=None, min_length=1, max_length=30)
    target_value: int | None = Field(default=None, gt=0, le=1_000_000)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: Literal["open", "closed"] | None = None


class ChallengeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: str
    sport: str
    unit: str
    target_value: int
    starts_at: datetime
    ends_at: datetime
    status: str
    created_by: int
    participant_count: int = 0


class ProgressIn(BaseModel):
    value: int = Field(gt=0, le=1_000_000)
    note: str = Field(default="", max_length=240)


class ProgressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    value: int
    note: str
    recorded_at: datetime


class LeaderboardRow(BaseModel):
    user_id: int
    display_name: str
    total: int
    target_value: int
    completed: bool
