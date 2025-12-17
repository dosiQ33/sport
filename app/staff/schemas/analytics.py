"""Staff Analytics Schemas - For club analytics and dashboard data"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date


class SectionStats(BaseModel):
    """Статистика по секции"""
    id: int
    name: str
    students_count: int = 0
    groups_count: int = 0
    
    class Config:
        from_attributes = True


class ClubAnalyticsResponse(BaseModel):
    """Аналитика клуба"""
    club_id: int
    club_name: str
    
    # Student stats
    total_students: int = 0
    active_students: int = 0
    new_students_this_month: int = 0
    
    # Training stats
    trainings_this_month: int = 0
    trainings_conducted: int = 0
    trainings_scheduled: int = 0
    trainings_cancelled: int = 0
    
    # Section breakdown
    sections: List[SectionStats] = []
    
    # Period info
    period_start: date
    period_end: date


class CoachAnalyticsResponse(BaseModel):
    """Аналитика тренера"""
    coach_id: int
    coach_name: str
    
    # Student stats
    total_students: int = 0
    
    # Training stats
    trainings_this_month: int = 0
    trainings_conducted: int = 0
    trainings_scheduled: int = 0
    trainings_cancelled: int = 0
    
    # Sections/Groups
    sections_count: int = 0
    groups_count: int = 0
    
    # Period info
    period_start: date
    period_end: date


class DashboardSummary(BaseModel):
    """Общая сводка для dashboard"""
    # Totals across all accessible clubs
    total_clubs: int = 0
    total_sections: int = 0
    total_groups: int = 0
    total_students: int = 0
    
    # This month
    trainings_this_month: int = 0
    new_students_this_month: int = 0
    
    # Period info
    period_start: date
    period_end: date
