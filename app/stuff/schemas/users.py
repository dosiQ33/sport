from datetime import datetime
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict


class UserPreferences(BaseModel):
    language: Optional[str] = Field("ru", pattern=r"^[a-z]{2}$")
    dark_mode: Optional[bool] = False
    notifications: Optional[bool] = True
    timezone: Optional[str] = "UTC+5"

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v and v not in ["ru", "en", "kz", "uz", "ky"]:  # Add supported languages
            raise ValueError("Unsupported language code")
        return v


class UserBase(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    telegram_id: int = Field(..., gt=0, description="Telegram user ID must be positive")
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    phone_number: str = Field(
        ..., min_length=10, max_length=30, description="Phone number is required"
    )
    username: Optional[str] = Field(None, max_length=64)
    photo_url: Optional[str] = Field(None, max_length=512)
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v:
            if not re.match(r"^[a-zA-Z0-9_]{5,32}$", v):
                raise ValueError(
                    "Username must be 5-32 characters, alphanumeric and underscore only"
                )
        return v


class UserCreate(BaseModel):
    contact_init_data: str = Field(
        ..., description="Telegram contact initData string containing phone number"
    )
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)


class UserUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    phone_number: Optional[str] = Field(None, min_length=10, max_length=30)
    username: Optional[str] = Field(None, max_length=64)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v:
            if not re.match(r"^[a-zA-Z0-9_]{5,32}$", v):
                raise ValueError(
                    "Username must be 5-32 characters, alphanumeric and underscore only"
                )
        return v


class UserRead(UserBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserFilters(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_number: Optional[str] = Field(None, min_length=1, max_length=30)
    username: Optional[str] = Field(None, min_length=1, max_length=64)


class UserListResponse(BaseModel):
    users: list[UserRead]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    size: int = Field(..., ge=1, le=100)
    pages: int = Field(..., ge=1)
    filters: Optional[UserFilters] = None


class PreferencesUpdate(BaseModel):
    language: Optional[str] = None
    dark_mode: Optional[bool] = None
    notifications: Optional[bool] = None
    timezone: Optional[str] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v and v not in ["ru", "en", "kz", "uz", "ky"]:  # Add supported languages
            raise ValueError("Unsupported language code")
        return v
