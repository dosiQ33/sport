from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, ConfigDict


# Types
PackageType = Literal["full_club", "full_section", "single_group", "multiple_groups"]
PaymentType = Literal["monthly", "semi_annual", "annual", "session_pack"]


class TariffCreatorInfo(BaseModel):
    """Info about tariff creator"""
    id: int
    first_name: str
    last_name: str
    username: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class TariffBase(BaseModel):
    """Base tariff schema"""
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    type: PackageType = Field(default="single_group")
    payment_type: PaymentType = Field(default="monthly")
    price: float = Field(..., ge=0)
    club_ids: List[int] = Field(default_factory=list)
    section_ids: List[int] = Field(default_factory=list)
    group_ids: List[int] = Field(default_factory=list)
    sessions_count: Optional[int] = Field(None, ge=1, le=1000)
    validity_days: Optional[int] = Field(None, ge=1, le=365)
    features: List[str] = Field(default_factory=list, description="List of included features")
    active: bool = Field(default=True)


class TariffCreate(TariffBase):
    """Schema for creating a tariff"""
    pass


class TariffUpdate(BaseModel):
    """Schema for updating a tariff"""
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=1000)
    type: Optional[PackageType] = None
    payment_type: Optional[PaymentType] = None
    price: Optional[float] = Field(None, ge=0)
    club_ids: Optional[List[int]] = None
    section_ids: Optional[List[int]] = None
    group_ids: Optional[List[int]] = None
    sessions_count: Optional[int] = Field(None, ge=1, le=1000)
    validity_days: Optional[int] = Field(None, ge=1, le=365)
    features: Optional[List[str]] = None
    active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class TariffRead(TariffBase):
    """Schema for reading a tariff"""
    id: int
    created_by_id: Optional[int] = None
    created_by: Optional[TariffCreatorInfo] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TariffListResponse(BaseModel):
    """Paginated list of tariffs"""
    tariffs: List[TariffRead]
    total: int
    page: int
    size: int
    pages: int
    filters: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)
