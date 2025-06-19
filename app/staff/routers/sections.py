from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.staff.schemas.sections import SectionCreate, SectionUpdate, SectionRead
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.core.exceptions import ResourceNotFoundError
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
    # Новые функции для проверки лимитов и прав
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
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем try/catch блок
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
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем try/catch блок
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
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

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
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем try/catch блок
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
    """
    # Get user from database to ensure they exist as staff
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем большой try/catch блок - exception handler справится
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
    sections = await get_sections_by_coach(db, coach_id, skip=skip, limit=limit)
    return sections


@router.get("/my", response_model=List[SectionRead])
@limiter.limit("20/minute")
async def get_my_sections(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    sections = await get_sections_by_coach(db, user_staff.id)
    return sections


@router.get("/{section_id}", response_model=SectionRead)
@limiter.limit("30/minute")
async def get_section(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    db: AsyncSession = Depends(get_session),
):
    section = await get_section_by_id(db, section_id)
    if not section:
        raise ResourceNotFoundError("Section not found", error_code="SECTION_NOT_FOUND")
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
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    # Убираем try/catch блок - exception handler справится
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
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    # Убираем try/catch блок - exception handler справится
    deleted = await delete_section(db, section_id, user_staff.id)


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
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    # Убираем try/catch блок - exception handler справится
    db_section = await toggle_section_status(db, section_id, user_staff.id)
    return db_section


@router.get("/{section_id}/stats")
@limiter.limit("20/minute")
async def get_section_stats(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    db: AsyncSession = Depends(get_session),
):
    stats = await get_section_statistics(db, section_id)
    if not stats:
        raise ResourceNotFoundError("Section not found", error_code="SECTION_NOT_FOUND")
    return stats
