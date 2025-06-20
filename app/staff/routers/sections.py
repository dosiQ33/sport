from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.staff.schemas.sections import SectionCreate, SectionUpdate, SectionRead
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.sections import (
    get_section_by_id,
    get_sections_by_club,
    get_sections_by_coach,
    get_sections_paginated,
    create_section,
    update_section,
    delete_section,
    get_section_statistics,
    toggle_section_status,
    # Функции для проверки лимитов и прав
    check_user_sections_limit_before_create,
    check_user_club_section_permission,
    check_user_can_create_section_in_club,
    get_user_sections_stats,
)

router = APIRouter(prefix="/sections", tags=["Sections"])


@router.get("/limits/check")
@limiter.limit("20/minute")
async def check_sections_creation_limits(
    request: Request,
    club_id: Optional[int] = Query(None, description="Check limits for specific club"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Проверить лимиты на создание секций для текущего пользователя.

    Опционально можно указать club_id для проверки лимитов в конкретном клубе.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Валидация и ошибки обрабатываются в CRUD
    limits_info = await check_user_sections_limit_before_create(
        db, user_staff.id, club_id
    )
    return limits_info


@router.get("/permissions/club/{club_id}")
@limiter.limit("20/minute")
async def check_club_section_permissions(
    request: Request,
    club_id: int = Path(..., description="Club ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Проверить права пользователя на создание секций в конкретном клубе.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Валидация и ошибки обрабатываются в CRUD
    permission_info = await check_user_club_section_permission(
        db, user_staff.id, club_id
    )
    return permission_info


@router.get("/can-create/club/{club_id}")
@limiter.limit("20/minute")
async def check_can_create_section_in_club(
    request: Request,
    club_id: int = Path(..., description="Club ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Комплексная проверка: может ли пользователь создать секцию в конкретном клубе.

    Проверяет и лимиты, и права доступа.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Все проверки происходят в CRUD
    check_result = await check_user_can_create_section_in_club(
        db, user_staff.id, club_id
    )
    return check_result


@router.get("/stats/my")
@limiter.limit("20/minute")
async def get_my_sections_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить статистику по секциям текущего пользователя.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Валидация и ошибки обрабатываются в CRUD
    stats = await get_user_sections_stats(db, user_staff.id)
    return stats


@router.post("/", response_model=SectionRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_new_section(
    request: Request,
    section: SectionCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new section in a club.

    Automatically checks:
    - User permissions in the club (owner/admin)
    - User section creation limits
    - Section name uniqueness within club

    - **club_id**: ID of the club where section will be created
    - **name**: Section name (required, must be unique within club)
    - **level**: Skill level (beginner, intermediate, advanced, pro)
    - **capacity**: Maximum number of students (optional)
    - **price**: Base price for the section (optional)
    - **duration_min**: Duration in minutes (default: 60)
    - **coach_id**: ID of the coach assigned to this section (optional)
    - **tags**: List of tags (e.g., ["boxing", "kids"])
    - **schedule**: JSON object with schedule information
    - **active**: Whether section is active (default: true)
    """
    # Get user from database to ensure they exist as staff
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # Все ошибки бизнес-логики обрабатываются в CRUD автоматически
    db_section = await create_section(db, section, user_staff.id)
    return db_section


@router.get("/", response_model=List[SectionRead])
@limiter.limit("30/minute")
async def get_sections_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    club_id: Optional[int] = Query(None, description="Filter by club ID"),
    coach_id: Optional[int] = Query(None, description="Filter by coach ID"),
    level: Optional[str] = Query(None, description="Filter by skill level"),
    name: Optional[str] = Query(
        None, description="Filter by section name (partial match)"
    ),
    active_only: bool = Query(True, description="Show only active sections"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of sections with optional filters.

    - **page**: Page number (starts from 1)
    - **size**: Number of sections per page (max 100)
    - **club_id**: Filter by specific club
    - **coach_id**: Filter by specific coach
    - **level**: Filter by skill level (beginner, intermediate, advanced, pro)
    - **name**: Filter by section name (partial match)
    - **active_only**: Show only active sections (default: true)
    """
    skip = (page - 1) * size

    # Валидация параметров происходит в CRUD
    sections, total = await get_sections_paginated(
        db,
        skip=skip,
        limit=size,
        club_id=club_id,
        coach_id=coach_id,
        level=level,
        active_only=active_only,
        name=name,
    )

    return sections


@router.get("/club/{club_id}", response_model=List[SectionRead])
@limiter.limit("30/minute")
async def get_club_sections(
    request: Request,
    club_id: int = Path(..., description="Club ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return"),
    active_only: bool = Query(True, description="Show only active sections"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all sections for a specific club.

    - **club_id**: ID of the club
    - **skip**: Number of sections to skip (for pagination)
    - **limit**: Maximum number of sections to return
    - **active_only**: Show only active sections
    """
    # Валидация происходит в CRUD
    sections = await get_sections_by_club(
        db, club_id, skip=skip, limit=limit, active_only=active_only
    )
    return sections


@router.get("/coach/{coach_id}", response_model=List[SectionRead])
@limiter.limit("30/minute")
async def get_coach_sections(
    request: Request,
    coach_id: int = Path(..., description="Coach ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all sections coached by a specific user.

    - **coach_id**: ID of the coach
    - **skip**: Number of sections to skip (for pagination)
    - **limit**: Maximum number of sections to return
    """
    # Валидация происходит в CRUD
    sections = await get_sections_by_coach(db, coach_id, skip=skip, limit=limit)
    return sections


@router.get("/my", response_model=List[SectionRead])
@limiter.limit("20/minute")
async def get_my_sections(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all sections coached by the authenticated user.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    sections = await get_sections_by_coach(db, user_staff.id)
    return sections


@router.get("/{section_id}", response_model=SectionRead)
@limiter.limit("30/minute")
async def get_section(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get section details by ID.

    - **section_id**: Unique section identifier
    """
    # Валидация и ошибки обрабатываются в CRUD
    section = await get_section_by_id(db, section_id)
    return section


@router.put("/{section_id}", response_model=SectionRead)
@limiter.limit("10/minute")
async def update_section_details(
    request: Request,
    section_update: SectionUpdate,
    section_id: int = Path(..., description="Section ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update section details. Only club owner, admins, or the assigned coach can update.

    - **section_id**: Unique section identifier
    - All fields are optional in update
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Все проверки разрешений и ошибки обрабатываются в CRUD
    db_section = await update_section(db, section_id, section_update, user_staff.id)
    return db_section


@router.delete("/{section_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_section_route(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Delete a section. Only club owner or admins can delete.

    - **section_id**: Unique section identifier

    ⚠️ **Warning**: This action is irreversible and will also delete all related data.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Все проверки разрешений и ошибки обрабатываются в CRUD
    await delete_section(db, section_id, user_staff.id)
    # FastAPI автоматически вернет 204 No Content


@router.patch("/{section_id}/toggle-status", response_model=SectionRead)
@limiter.limit("10/minute")
async def toggle_section_status_route(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Toggle section active status (activate/deactivate).

    - **section_id**: Unique section identifier

    This is useful for temporarily disabling sections without deleting them.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Все проверки разрешений и ошибки обрабатываются в CRUD
    db_section = await toggle_section_status(db, section_id, user_staff.id)
    return db_section


@router.get("/{section_id}/stats")
@limiter.limit("20/minute")
async def get_section_stats(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get section statistics including enrollment info.

    - **section_id**: Unique section identifier

    Returns basic statistics about the section.
    """
    # Валидация и ошибки обрабатываются в CRUD
    stats = await get_section_statistics(db, section_id)
    return stats
