"""Student Schedule Schemas - For viewing upcoming sessions"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, time, datetime
from enum import Enum


class SessionStatus(str, Enum):
    """Session status from student perspective"""
    scheduled = "scheduled"
    booked = "booked"
    full = "full"
    cancelled = "cancelled"


class SessionRead(BaseModel):
    """Training session for student view"""
    id: int
    
    # Section/Group info
    section_name: str
    group_name: Optional[str] = None
    
    # Coach info
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    
    # Club info
    club_id: int
    club_name: Optional[str] = None
    club_address: Optional[str] = None
    
    # Schedule
    date: date
    time: str  # Formatted time string HH:MM
    duration_minutes: int = 90
    
    # Location
    location: Optional[str] = None
    
    # Participants
    participants_count: int = 0
    max_participants: Optional[int] = None
    
    # Status
    status: SessionStatus
    is_booked: bool = False
    is_in_waitlist: bool = False
    
    # Notes
    notes: Optional[str] = None
    
    class Config:
        from_attributes = True


class SessionListResponse(BaseModel):
    """Response with session list"""
    sessions: List[SessionRead]
    total: int


class BookSessionRequest(BaseModel):
    """Request to book a session"""
    lesson_id: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "lesson_id": 1
            }
        }


class BookSessionResponse(BaseModel):
    """Response after booking"""
    success: bool
    message: str
    booking_id: Optional[int] = None


class CancelBookingRequest(BaseModel):
    """Request to cancel booking"""
    lesson_id: int


class CancelBookingResponse(BaseModel):
    """Response after cancellation"""
    success: bool
    message: str


class TrainerInfo(BaseModel):
    """Trainer information"""
    id: int
    name: str
    club_id: Optional[int] = None
    
    class Config:
        from_attributes = True


class ScheduleFilters(BaseModel):
    """Filters for schedule"""
    club_id: Optional[int] = None
    section_id: Optional[int] = None
    trainer_id: Optional[int] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    only_my_sessions: bool = False


class ParticipantInfo(BaseModel):
    """Information about a session participant"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    photo_url: Optional[str] = None
    is_current_user: bool = False
    
    class Config:
        from_attributes = True


class SessionParticipantsResponse(BaseModel):
    """Response with list of session participants"""
    lesson_id: int
    participants: List[ParticipantInfo]
    total: int
    max_participants: Optional[int] = None
