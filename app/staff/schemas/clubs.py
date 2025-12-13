from datetime import datetime
from typing import Any, Optional, List
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, computed_field

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
    whatsapp_url: Optional[str] = Field(
        None, max_length=255, description="WhatsApp contact URL or number"
    )
    
    # Working hours
    working_hours_start: Optional[str] = Field(
        "09:00", max_length=5, description="Opening time (HH:MM)"
    )
    working_hours_end: Optional[str] = Field(
        "21:00", max_length=5, description="Closing time (HH:MM)"
    )
    
    # Tags
    tags: Optional[List[str]] = Field(
        default_factory=list, description="List of tags for categorization"
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

    @field_validator("working_hours_start", "working_hours_end")
    @classmethod
    def validate_working_hours(cls, v):
        if v:
            if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
                raise ValidationError("Working hours must be in HH:MM format (e.g., 09:00)")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v:
            # Ensure tags are unique and not too long
            unique_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            if len(unique_tags) > 20:
                raise ValidationError("Maximum 20 tags allowed")
            for tag in unique_tags:
                if len(tag) > 50:
                    raise ValidationError("Each tag must be 50 characters or less")
            return unique_tags
        return v or []


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
    whatsapp_url: Optional[str] = Field(None, max_length=255)
    
    working_hours_start: Optional[str] = Field(None, max_length=5)
    working_hours_end: Optional[str] = Field(None, max_length=5)
    
    tags: Optional[List[str]] = Field(None)

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

    @field_validator("working_hours_start", "working_hours_end")
    @classmethod
    def validate_working_hours(cls, v):
        if v:
            if not re.match(r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$", v):
                raise ValidationError("Working hours must be in HH:MM format")
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            unique_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            if len(unique_tags) > 20:
                raise ValidationError("Maximum 20 tags allowed")
            return unique_tags
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
    
    # Computed property for formatted working hours
    @computed_field
    @property
    def working_hours(self) -> str:
        start = self.working_hours_start or "09:00"
        end = self.working_hours_end or "21:00"
        return f"{start} - {end}"

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
