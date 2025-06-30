from datetime import datetime
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.core.exceptions import ValidationError


class UserLimits(BaseModel):
    """Схема для лимитов пользователя"""

    clubs: int = Field(0, ge=0, le=10, description="Maximum number of clubs")
    sections: int = Field(0, ge=0, le=30, description="Maximum number of sections")

    model_config = ConfigDict(from_attributes=True)


class UserStaffPreferences(BaseModel):
    language: Optional[str] = Field("ru", pattern=r"^[a-z]{2}$")
    dark_mode: Optional[bool] = False
    notifications: Optional[bool] = True

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v and v not in ["ru", "en", "kz", "uz", "ky"]:  # Add supported languages
            raise ValidationError("Unsupported language code")
        return v


class UserStaffBase(BaseModel):
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
    limits: UserLimits = Field(default_factory=lambda: UserLimits(clubs=0, sections=0))

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v:
            if not re.match(r"^[a-zA-Z0-9_]{5,32}$", v):
                raise ValidationError(
                    "Username must be 5-32 characters, alphanumeric and underscore only"
                )
        return v


class UserStaffCreate(BaseModel):
    contact_init_data: str = Field(
        ..., description="Telegram contact initData string containing phone number"
    )
    preferences: Optional[Dict[str, Any]] = Field(default_factory=dict)


class UserStaffUpdate(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, max_length=50)
    username: Optional[str] = Field(None, max_length=64)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v):
        if v:
            if not re.match(r"^[a-zA-Z0-9_]{5,32}$", v):
                raise ValidationError(
                    "Username must be 5-32 characters, alphanumeric and underscore only"
                )
        return v


class UserStaffRead(UserStaffBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserStaffFilters(BaseModel):
    first_name: Optional[str] = Field(None, min_length=1, max_length=50)
    last_name: Optional[str] = Field(None, min_length=1, max_length=50)
    phone_number: Optional[str] = Field(None, min_length=1, max_length=30)
    username: Optional[str] = Field(None, min_length=1, max_length=64)


class UserStaffListResponse(BaseModel):
    users: list[UserStaffRead]
    total: int = Field(..., ge=0)
    page: int = Field(..., ge=1)
    size: int = Field(..., ge=1, le=100)
    pages: int = Field(..., ge=1)
    filters: Optional[UserStaffFilters] = None


class UserStaffPreferencesUpdate(BaseModel):
    language: Optional[str] = None
    dark_mode: Optional[bool] = None
    notifications: Optional[bool] = None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v):
        if v and v not in ["ru", "en", "kz", "uz", "ky"]:  # Add supported languages
            raise ValidationError("Unsupported language code")
        return v


# Новые схемы для работы с лимитами
class UserLimitsUpdate(BaseModel):
    """Схема для обновления лимитов пользователя (только для суперадмина)"""

    clubs: Optional[int] = Field(None, ge=0, le=10)
    sections: Optional[int] = Field(None, ge=0, le=30)

    model_config = ConfigDict(from_attributes=True)


class UserLimitsResponse(BaseModel):
    """Ответ с информацией о лимитах и текущем использовании"""

    user_id: int
    limits: UserLimits
    current_usage: Dict[str, int] = Field(description="Current clubs/sections count")
    available: Dict[str, int] = Field(description="Available slots")

    model_config = ConfigDict(from_attributes=True)
