from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict

from app.staff.models.roles import RoleType


class ClubRole(BaseModel):
    """Информация о роли пользователя в конкретном клубе"""

    club_id: int
    club_name: str
    role: RoleType
    joined_at: datetime
    is_active: bool
    sections_count: int = Field(0, description="Количество секций (для тренеров)")

    model_config = ConfigDict(from_attributes=True)


class TeamMember(BaseModel):
    """Участник команды с информацией о всех его ролях в общих клубах"""

    id: int
    telegram_id: Optional[int] = None
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: str
    photo_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    clubs_and_roles: List[ClubRole] = Field(
        default_factory=list, description="Роли пользователя в общих клубах"
    )

    model_config = ConfigDict(from_attributes=True)


class TeamListResponse(BaseModel):
    """Ответ со списком участников команды"""

    staff_members: List[TeamMember]
    total: int = Field(..., ge=0, description="Общее количество участников")
    page: int = Field(..., ge=1, description="Текущая страница")
    size: int = Field(..., ge=1, le=100, description="Размер страницы")
    pages: int = Field(..., ge=1, description="Общее количество страниц")

    applied_filters: Optional[Dict[str, Any]] = Field(
        None, description="Примененные фильтры"
    )

    current_user_clubs: List[Dict[str, Any]] = Field(
        default_factory=list, description="Клубы текущего пользователя для контекста"
    )

    model_config = ConfigDict(from_attributes=True)


class TeamFilters(BaseModel):
    """Фильтры для поиска участников команды"""

    club_id: Optional[int] = Field(None, gt=0, description="Фильтр по клубу")
    role: Optional[RoleType] = Field(None, description="Фильтр по роли")
    name: Optional[str] = Field(
        None, min_length=1, max_length=100, description="Поиск по имени"
    )
    section_id: Optional[int] = Field(
        None, gt=0, description="Тренеры конкретной секции"
    )
    active_only: bool = Field(True, description="Только активные роли")

    model_config = ConfigDict(from_attributes=True)


class TeamStats(BaseModel):
    """Статистика по команде"""

    total_members: int
    by_role: Dict[str, int] = Field(description="Количество по ролям")
    by_club: Dict[str, int] = Field(description="Количество по клубам")
    active_members: int

    model_config = ConfigDict(from_attributes=True)
