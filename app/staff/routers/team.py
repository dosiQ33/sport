import math
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.staff.schemas.team import TeamListResponse, TeamFilters, TeamStats, TeamMember
from app.staff.models.roles import RoleType
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.team import (
    get_team_members_paginated,
    get_user_clubs_info,
    get_team_stats,
)

router = APIRouter(prefix="/team", tags=["Team"])


@router.get("/", response_model=TeamListResponse)
@limiter.limit("30/minute")
async def get_team_members(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    # Фильтры
    club_id: Optional[int] = Query(None, gt=0, description="Filter by specific club"),
    role: Optional[RoleType] = Query(
        None, description="Filter by role (owner, admin, coach)"
    ),
    name: Optional[str] = Query(
        None, min_length=1, max_length=100, description="Search by name (partial match)"
    ),
    section_id: Optional[int] = Query(
        None, gt=0, description="Show coaches of specific section"
    ),
    active_only: bool = Query(True, description="Show only active team members"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get team members from all clubs where current user works.

    Shows all staff members from shared clubs, regardless of current user's role.
    Each team member includes information about their roles in shared clubs only.

    **Filters:**
    - **club_id**: Show team from specific club only
    - **role**: Filter by role (owner, admin, coach)
    - **name**: Search by first name or last name (partial match)
    - **section_id**: Show coaches assigned to specific section
    - **active_only**: Include only active team members (default: true)

    **Response includes:**
    - Paginated list of team members
    - Each member's roles in shared clubs only
    - Information about current user's clubs for context
    """

    # Получаем пользователя
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Создаем объект фильтров
    filters = TeamFilters(
        club_id=club_id,
        role=role,
        name=name,
        section_id=section_id,
        active_only=active_only,
    )

    skip = (page - 1) * size

    # Получаем данные с пагинацией
    team_members, total = await get_team_members_paginated(
        db, user_staff.id, skip=skip, limit=size, filters=filters
    )

    # Получаем информацию о клубах пользователя для контекста
    user_clubs_info = await get_user_clubs_info(db, user_staff.id)

    pages = math.ceil(total / size) if total > 0 else 1

    # Формируем информацию о примененных фильтрах
    applied_filters = {}
    if club_id:
        applied_filters["club_id"] = club_id
    if role:
        applied_filters["role"] = role.value
    if name:
        applied_filters["name"] = name
    if section_id:
        applied_filters["section_id"] = section_id
    if not active_only:
        applied_filters["active_only"] = active_only

    return TeamListResponse(
        staff_members=team_members,
        total=total,
        page=page,
        size=size,
        pages=pages,
        applied_filters=applied_filters if applied_filters else None,
        current_user_clubs=user_clubs_info,
    )


@router.get("/stats", response_model=TeamStats)
@limiter.limit("20/minute")
async def get_team_statistics(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get team statistics for all shared clubs.

    Returns:
    - Total number of team members
    - Breakdown by roles (owner, admin, coach)
    - Breakdown by clubs
    - Number of active members

    Statistics include only team members from clubs where current user works.
    """

    # Получаем пользователя
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Получаем статистику
    stats_data = await get_team_stats(db, user_staff.id)

    return TeamStats(**stats_data)


@router.get("/my-clubs")
@limiter.limit("30/minute")
async def get_my_clubs_context(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get information about clubs where current user works.

    Useful for understanding the context of team data and available filters.

    Returns:
    - List of clubs with user's role in each club
    - Can be used to populate filter dropdowns in UI
    """

    # Получаем пользователя
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Получаем информацию о клубах
    clubs_info = await get_user_clubs_info(db, user_staff.id)

    return {
        "user_id": user_staff.id,
        "clubs": clubs_info,
        "total_clubs": len(clubs_info),
        "message": "These are the clubs where you work and can see team members",
    }
