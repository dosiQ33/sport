"""Student Memberships Schemas - For viewing enrollments from student perspective"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class MembershipStatus(str, Enum):
    """Membership status"""
    active = "active"
    frozen = "frozen"
    expired = "expired"
    cancelled = "cancelled"
    new = "new"
    scheduled = "scheduled"  # Scheduled to start after current membership ends


class MembershipRead(BaseModel):
    """Membership information for student"""
    id: int
    
    # Club info
    club_id: int
    club_name: str
    
    # Section/Group info
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    
    # Training type
    training_type: str = "Group"  # Group or Personal
    level: Optional[str] = None
    
    # Status
    status: MembershipStatus
    
    # Dates
    start_date: date
    end_date: date
    
    # Tariff info
    tariff_id: Optional[int] = None
    tariff_name: Optional[str] = None
    price: float = 0
    
    # Tariff status - indicates if the tariff was deleted
    # When true, freeze and extend are not allowed
    is_tariff_deleted: bool = False
    
    # Freeze info
    freeze_days_available: int = 0
    freeze_days_used: int = 0
    freeze_start_date: Optional[date] = None
    freeze_end_date: Optional[date] = None
    
    # Coach info
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class MembershipHistoryRead(BaseModel):
    """Historical membership record"""
    id: int
    
    club_id: int
    club_name: str
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    
    training_type: str = "Group"
    
    # Deactivation info
    deactivation_date: date
    reason: str  # expired, cancelled
    
    # Original dates
    start_date: date
    end_date: date
    
    class Config:
        from_attributes = True


class MembershipListResponse(BaseModel):
    """Response with list of memberships"""
    memberships: List[MembershipRead]
    total: int


class MembershipHistoryResponse(BaseModel):
    """Response with membership history"""
    history: List[MembershipHistoryRead]
    total: int


class FreezeMembershipRequest(BaseModel):
    """Request to freeze membership"""
    enrollment_id: int
    start_date: date
    end_date: date
    
    class Config:
        json_schema_extra = {
            "example": {
                "enrollment_id": 1,
                "start_date": "2024-01-15",
                "end_date": "2024-01-20"
            }
        }


class UnfreezeMembershipRequest(BaseModel):
    """Request to unfreeze membership"""
    enrollment_id: int


class MembershipStatsResponse(BaseModel):
    """Membership statistics"""
    active_memberships: int = 0
    frozen_memberships: int = 0
    total_memberships: int = 0
    days_until_expiry: Optional[int] = None
    freeze_days_available: int = 0
