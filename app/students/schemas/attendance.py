"""Student Attendance Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime, time
from enum import Enum


class AttendanceStatus(str, Enum):
    """Attendance status"""
    attended = "attended"
    missed = "missed"
    late = "late"
    excused = "excused"


class CheckInRequest(BaseModel):
    """Request to check in"""
    latitude: Optional[float] = Field(None, ge=-90, le=90, description="User latitude")
    longitude: Optional[float] = Field(None, ge=-180, le=180, description="User longitude")
    lesson_id: Optional[int] = Field(None, description="Optional lesson to check in to")
    
    class Config:
        json_schema_extra = {
            "example": {
                "latitude": 43.2389,
                "longitude": 76.8897,
                "lesson_id": None
            }
        }


class CheckInResponse(BaseModel):
    """Response after check-in"""
    success: bool
    message: str
    attendance_id: Optional[int] = None
    checkin_time: Optional[datetime] = None
    club_name: Optional[str] = None
    section_name: Optional[str] = None


class AttendanceRecordRead(BaseModel):
    """Attendance record for display"""
    id: int
    
    # Context
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    
    # Check-in details
    checkin_date: date
    checkin_time: Optional[time] = None
    
    # Status
    status: AttendanceStatus
    
    # Lesson info if available
    lesson_id: Optional[int] = None
    lesson_time: Optional[str] = None
    coach_name: Optional[str] = None
    
    notes: Optional[str] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class AttendanceListResponse(BaseModel):
    """Response with attendance list"""
    records: List[AttendanceRecordRead]
    total: int
    page: int = 1
    size: int = 20
    pages: int = 1


class AttendanceStatsResponse(BaseModel):
    """Attendance statistics"""
    visits_this_month: int = 0
    missed_this_month: int = 0
    average_attendance: float = 0.0
    total_visits: int = 0
    streak_days: int = 0
    last_visit_date: Optional[date] = None
