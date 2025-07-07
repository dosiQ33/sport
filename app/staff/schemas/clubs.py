from datetime import datetime
from typing import Any, Optional
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import ValidationError
from app.core.validations import clean_phone_number


class ClubBase(BaseModel):
    """Base club schema with common fields."""

    name: str = Field(
        ..., min_length=2, max_length=100, description="Club name (2-100 characters)"
    )
    description: Optional[str] = Field(
        None, max_length=1000, description="Club description"
    )
    city: Optional[str] = Field(
        None, max_length=80, description="City where club is located"
    )
    address: Optional[str] = Field(None, max_length=255, description="Physical address")

    logo_url: Optional[str] = Field(None, max_length=255, description="Logo image URL")
    cover_url: Optional[str] = Field(
        None, max_length=255, description="Cover image URL"
    )

    phone: Optional[str] = Field(
        None, max_length=32, description="Contact phone number"
    )
    telegram_url: Optional[str] = Field(
        None, max_length=255, description="Telegram channel/group URL"
    )
    instagram_url: Optional[str] = Field(
        None, max_length=255, description="Instagram profile URL"
    )

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValidationError("Club name cannot be empty")

        # Allow letters, numbers, spaces, and basic punctuation
        if not re.match(r"^[a-zA-Zа-яА-Я0-9\s\-_.()]+$", v):
            raise ValidationError("Club name contains invalid characters")

        return v.strip()

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v:
            return clean_phone_number(v)
        return v

    @field_validator("telegram_url")
    @classmethod
    def validate_telegram_url(cls, v):
        if v:
            if not (
                v.startswith("https://t.me/") or v.startswith("https://telegram.me/")
            ):
                raise ValidationError(
                    "Telegram URL must start with https://t.me/ or https://telegram.me/"
                )
        return v

    @field_validator("instagram_url")
    @classmethod
    def validate_instagram_url(cls, v):
        if v:
            if not v.startswith("https://instagram.com/") and not v.startswith(
                "https://www.instagram.com/"
            ):
                raise ValidationError(
                    "Instagram URL must start with https://instagram.com/ or https://www.instagram.com/"
                )
        return v


class ClubCreate(ClubBase):
    """Schema for creating a new club."""

    # All fields inherited from ClubBase, name is required, others optional
    pass


class ClubUpdate(BaseModel):
    """Schema for updating club details - all fields optional."""

    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    city: Optional[str] = Field(None, max_length=80)
    address: Optional[str] = Field(None, max_length=255)

    logo_url: Optional[str] = Field(None, max_length=255)
    cover_url: Optional[str] = Field(None, max_length=255)

    phone: Optional[str] = Field(None, max_length=32)
    telegram_url: Optional[str] = Field(None, max_length=255)
    instagram_url: Optional[str] = Field(None, max_length=255)

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    # Same validators as ClubBase but for optional fields
    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValidationError("Club name cannot be empty")
            if not re.match(r"^[a-zA-Zа-яА-Я0-9\s\-_.()]+$", v):
                raise ValidationError("Club name contains invalid characters")
            return v.strip()
        return v

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v):
        if v:
            clean_phone = re.sub(r"\s+", "", v)
            if not re.match(r"^\+?[1-9]\d{7,20}$", clean_phone):
                raise ValidationError("Invalid phone number format")
        return v

    @field_validator("telegram_url")
    @classmethod
    def validate_telegram_url(cls, v):
        if v:
            if not (
                v.startswith("https://t.me/") or v.startswith("https://telegram.me/")
            ):
                raise ValidationError(
                    "Telegram URL must start with https://t.me/ or https://telegram.me/"
                )
        return v

    @field_validator("instagram_url")
    @classmethod
    def validate_instagram_url(cls, v):
        if v:
            if not v.startswith("https://instagram.com/") and not v.startswith(
                "https://www.instagram.com/"
            ):
                raise ValidationError(
                    "Instagram URL must start with https://instagram.com/ or https://www.instagram.com/"
                )
        return v


class ClubOwnerInfo(BaseModel):
    """Basic owner information for club response."""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ClubRead(ClubBase):
    """Schema for club response with additional metadata."""

    id: int
    owner_id: Optional[int] = None
    owner: Optional[ClubOwnerInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ClubListResponse(BaseModel):
    """Response schema for paginated club list."""

    clubs: list[ClubRead]
    total: int = Field(..., ge=0, description="Total number of clubs")
    page: int = Field(..., ge=1, description="Current page number")
    size: int = Field(..., ge=1, le=50, description="Number of items per page")
    pages: int = Field(..., ge=1, description="Total number of pages")
    filters: Optional[dict[str, Any]] = Field(None, description="Applied filters")

    model_config = ConfigDict(from_attributes=True)


class ClubStats(BaseModel):
    """Club statistics schema."""

    id: int
    name: str
    total_sections: int = 0
    total_coaches: int = 0
    total_students: int = 0
    active_sections: int = 0

    model_config = ConfigDict(from_attributes=True)
