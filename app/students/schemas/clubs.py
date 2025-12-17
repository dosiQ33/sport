"""Student Clubs Schemas - For viewing available clubs"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ClubCoachRead(BaseModel):
    """Coach info for club details"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    photo_url: Optional[str] = None
    specialization: Optional[str] = None  # Section name they coach
    
    class Config:
        from_attributes = True


class ClubSectionRead(BaseModel):
    """Section info for club details"""
    id: int
    name: str
    description: Optional[str] = None
    
    class Config:
        from_attributes = True


class ClubTariffRead(BaseModel):
    """Tariff info for club details"""
    id: int
    name: str
    description: Optional[str] = None
    type: str  # monthly, semi_annual, annual, session_pack
    payment_type: str  # monthly, quarterly, annual
    price: float
    duration_days: Optional[int] = None
    sessions_count: Optional[int] = None
    features: List[str] = []
    
    class Config:
        from_attributes = True


class ClubRead(BaseModel):
    """Club information for students"""
    id: int
    name: str
    description: Optional[str] = None
    
    # Location
    city: Optional[str] = None
    address: Optional[str] = None
    
    # Images
    logo_url: Optional[str] = None
    cover_url: Optional[str] = None
    
    # Contact
    phone: Optional[str] = None
    telegram_url: Optional[str] = None
    instagram_url: Optional[str] = None
    whatsapp_url: Optional[str] = None
    
    # Working hours
    working_hours: Optional[str] = None
    
    # Statistics
    sections_count: int = 0
    students_count: int = 0
    
    # Tags/Categories
    tags: List[str] = []
    
    class Config:
        from_attributes = True


class ClubDetailRead(ClubRead):
    """Detailed club information with sections, tariffs, and coaches"""
    sections: List[ClubSectionRead] = []
    tariffs: List[ClubTariffRead] = []
    coaches: List[ClubCoachRead] = []


class ClubListResponse(BaseModel):
    """Response with club list"""
    clubs: List[ClubRead]
    total: int
    page: int = 1
    size: int = 20
    pages: int = 1


class ClubLocationRead(BaseModel):
    """Club location for distance calculation"""
    id: int
    name: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    
    class Config:
        from_attributes = True


class NearestClubResponse(BaseModel):
    """Response with nearest club"""
    club: Optional[ClubLocationRead] = None
    distance_meters: Optional[float] = None
