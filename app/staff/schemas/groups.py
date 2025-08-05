from datetime import datetime
from typing import Any, Optional
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator

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

    # Тренер группы - ОБЯЗАТЕЛЬНОЕ ПОЛЕ
    coach_id: int = Field(..., gt=0, description="Coach ID is required")

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
    """Schema for updating group - all fields optional except coach_id if provided"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)

    schedule: Optional[dict[str, Any]] = None
    price: Optional[Decimal] = Field(None, ge=0)
    capacity: Optional[int] = Field(None, ge=1, le=100)
    level: Optional[str] = None

    coach_id: Optional[int] = Field(
        None, gt=0, description="Coach ID must be positive if provided"
    )
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
    club_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_section(cls, section):
        """Create SectionInfo from Section model with club data"""
        return cls(
            id=section.id,
            name=section.name,
            club_id=section.club_id,
            club_name=(
                section.club.name if hasattr(section, "club") and section.club else None
            ),
        )


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

    @classmethod
    def from_group(cls, group):
        """Create GroupRead from Group model"""
        section_info = None
        if group.section:
            section_info = SectionInfo.from_section(group.section)

        coach_info = None
        if group.coach:
            coach_info = CoachInfo.model_validate(group.coach)

        return cls(
            section_id=group.section_id,
            name=group.name,
            description=group.description,
            schedule=group.schedule,
            price=group.price,
            capacity=group.capacity,
            level=group.level,
            coach_id=group.coach_id,
            tags=group.tags,
            active=group.active,
            id=group.id,
            section=section_info,
            coach=coach_info,
            created_at=group.created_at,
            updated_at=group.updated_at,
        )


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
