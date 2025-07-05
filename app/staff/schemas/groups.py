from datetime import datetime
from typing import Any, Literal, Optional
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import ValidationError


class GroupBase(BaseModel):
    section_id: int = Field(..., gt=0, description="Section ID must be positive")
    name: str = Field(..., min_length=1, max_length=100, description="Group name")
    description: Optional[str] = Field(
        None, max_length=1000, description="Group description"
    )

    # Данные перенесенные из sections
    schedule: dict[str, Any] = Field(
        default_factory=dict, description="Schedule template (weekly pattern)"
    )
    price: Optional[Decimal] = Field(None, ge=0, description="Group price")
    capacity: Optional[int] = Field(None, ge=1, le=100, description="Maximum capacity")
    level: Optional[str] = Field(None, description="Skill level")

    # Тренер группы
    coach_id: Optional[int] = Field(None, gt=0, description="Coach ID")

    tags: list[str] = Field(default_factory=list, description="Group tags")
    active: bool = Field(True, description="Whether group is active")

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValidationError("Group name cannot be empty")
        return v.strip()

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v:
            # Remove duplicates and empty strings
            clean_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            return clean_tags
        return v


class GroupCreate(GroupBase):
    """Schema for creating a new group"""

    def model_validate(cls, v):
        instance = super().model_validate(v)
        instance.validate_age_range()
        return instance


class GroupUpdate(BaseModel):
    """Schema for updating group - all fields optional"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)

    schedule: Optional[dict[str, Any]] = None
    price: Optional[Decimal] = Field(None, ge=0)
    capacity: Optional[int] = Field(None, ge=1, le=100)
    level: Optional[str] = None

    coach_id: Optional[int] = Field(None, gt=0)
    tags: Optional[list[str]] = None
    active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValidationError("Group name cannot be empty")
            return v.strip()
        return v

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v):
        if v is not None:
            clean_tags = list(set(tag.strip().lower() for tag in v if tag.strip()))
            return clean_tags
        return v


# Basic info schemas for relationships
class SectionInfo(BaseModel):
    """Basic section information for group response"""

    id: int
    name: str
    club_id: int

    model_config = ConfigDict(from_attributes=True)


class CoachInfo(BaseModel):
    """Basic coach information for group response"""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GroupRead(GroupBase):
    """Schema for group response with additional metadata"""

    id: int
    section: Optional[SectionInfo] = None
    coach: Optional[CoachInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupListResponse(BaseModel):
    """Response schema for paginated group list"""

    groups: list[GroupRead]
    total: int = Field(..., ge=0, description="Total number of groups")
    page: int = Field(..., ge=1, description="Current page number")
    size: int = Field(..., ge=1, le=100, description="Number of items per page")
    pages: int = Field(..., ge=1, description="Total number of pages")
    filters: Optional[dict[str, Any]] = Field(None, description="Applied filters")

    model_config = ConfigDict(from_attributes=True)


class GroupStats(BaseModel):
    """Group statistics schema"""

    id: int
    name: str
    section_name: str
    coach_name: Optional[str] = None
    capacity: Optional[int] = None
    level: Optional[str] = None
    active: bool
    enrolled_students: int = 0  # Будет реализовано позже
    available_spots: Optional[int] = None
    price: Optional[Decimal] = None

    model_config = ConfigDict(from_attributes=True)


class GroupFilters(BaseModel):
    """Filters for group queries"""

    section_id: Optional[int] = Field(None, gt=0)
    club_id: Optional[int] = Field(None, gt=0)
    coach_id: Optional[int] = Field(None, gt=0)
    level: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    active_only: bool = True

    model_config = ConfigDict(from_attributes=True)
