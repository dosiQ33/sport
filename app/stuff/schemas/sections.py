from datetime import datetime
from typing import Any, Literal, Optional
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


SectionLevel = Literal["beginner", "intermediate", "advanced", "pro"]


class SectionBase(BaseModel):
    club_id: int = Field(..., gt=0, description="Club ID must be positive")
    name: str = Field(..., min_length=1, max_length=100, description="Section name")

    level: Optional[SectionLevel] = Field(None, description="Skill level")
    capacity: Optional[int] = Field(None, ge=1, le=1000, description="Maximum capacity")
    price: Optional[Decimal] = Field(None, ge=0, description="Base price")
    duration_min: int = Field(60, ge=15, le=480, description="Duration in minutes")

    coach_id: Optional[int] = Field(None, gt=0, description="Coach ID")
    tags: list[str] = Field(default_factory=list, description="Section tags")

    # JSON with schedule information
    schedule: dict[str, Any] = Field(default_factory=dict, description="Schedule data")

    active: bool = Field(True, description="Whether section is active")

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError("Section name cannot be empty")
        return v.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v:
            # Remove duplicates and empty strings
            clean_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            return clean_tags
        return v


class SectionCreate(SectionBase):
    """Schema for creating a new section"""

    pass


class SectionUpdate(BaseModel):
    """Schema for updating section - all fields optional"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    level: Optional[SectionLevel] = None
    capacity: Optional[int] = Field(None, ge=1, le=1000)
    price: Optional[Decimal] = Field(None, ge=0)
    duration_min: Optional[int] = Field(None, ge=15, le=480)
    coach_id: Optional[int] = Field(None, gt=0)
    tags: Optional[list[str]] = None
    schedule: Optional[dict[str, Any]] = None
    active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValueError("Section name cannot be empty")
            return v.strip()
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            # Remove duplicates and empty strings
            clean_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            return clean_tags
        return v


# Basic info schemas for relationships
class ClubInfo(BaseModel):
    """Basic club information for section response"""

    id: int
    name: str
    city: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class CoachInfo(BaseModel):
    """Basic coach information for section response"""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SectionRead(SectionBase):
    """Schema for section response with additional metadata"""

    id: int
    club: Optional[ClubInfo] = None
    coach: Optional[CoachInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SectionListResponse(BaseModel):
    """Response schema for paginated section list"""

    sections: list[SectionRead]
    total: int = Field(..., ge=0, description="Total number of sections")
    page: int = Field(..., ge=1, description="Current page number")
    size: int = Field(..., ge=1, le=100, description="Number of items per page")
    pages: int = Field(..., ge=1, description="Total number of pages")
    filters: Optional[dict[str, Any]] = Field(None, description="Applied filters")

    model_config = ConfigDict(from_attributes=True)


class SectionStats(BaseModel):
    """Section statistics schema"""

    id: int
    name: str
    club_name: Optional[str] = None
    coach_name: Optional[str] = None
    capacity: Optional[int] = None
    level: Optional[str] = None
    active: bool
    enrolled_students: int = 0
    available_spots: Optional[int] = None
    price: Optional[Decimal] = None
    duration_min: int = 60

    model_config = ConfigDict(from_attributes=True)


class SectionFilters(BaseModel):
    """Filters for section queries"""

    club_id: Optional[int] = Field(None, gt=0)
    coach_id: Optional[int] = Field(None, gt=0)
    level: Optional[SectionLevel] = None
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    active_only: bool = True

    model_config = ConfigDict(from_attributes=True)
