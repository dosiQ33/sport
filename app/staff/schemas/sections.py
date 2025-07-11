from datetime import datetime
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.exceptions import ValidationError


class SectionBase(BaseModel):
    club_id: int = Field(..., gt=0, description="Club ID must be positive")
    name: str = Field(..., min_length=1, max_length=100, description="Section name")
    description: Optional[str] = Field(
        None, max_length=1000, description="Section description"
    )

    # Главный тренер секции (координатор)
    coach_id: Optional[int] = Field(None, gt=0, description="Main coach ID")
    active: bool = Field(True, description="Whether section is active")

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValidationError("Section name cannot be empty")
        return v.strip()


class SectionCreate(SectionBase):
    """Schema for creating a new section"""

    pass


class SectionUpdate(BaseModel):
    """Schema for updating section - all fields optional"""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    coach_id: Optional[int] = Field(None, gt=0)
    active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v):
        if v is not None:
            if not v or not v.strip():
                raise ValidationError("Section name cannot be empty")
            return v.strip()
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


class GroupInfo(BaseModel):
    """Basic group information for section response"""

    id: int
    name: str
    level: Optional[str] = None
    capacity: Optional[int] = None
    price: Optional[Decimal] = None
    active: bool
    enrolled_students: int = 0  # Будет реализовано позже

    model_config = ConfigDict(from_attributes=True)


class SectionRead(SectionBase):
    """Schema for section response with additional metadata"""

    id: int
    club: Optional[ClubInfo] = None
    coach: Optional[CoachInfo] = None
    groups: list[GroupInfo] = Field(
        default_factory=list, description="Groups in this section"
    )
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
    coach_name: Optional[str] = None
    total_groups: int = 0
    active_groups: int = 0
    total_capacity: Optional[int] = None
    enrolled_students: int = 0  # Будет реализовано позже
    available_spots: Optional[int] = None
    active: bool

    model_config = ConfigDict(from_attributes=True)


class SectionFilters(BaseModel):
    """Filters for section queries"""

    club_id: Optional[int] = Field(None, gt=0)
    coach_id: Optional[int] = Field(None, gt=0)
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    active_only: bool = True

    model_config = ConfigDict(from_attributes=True)
