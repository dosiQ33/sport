import math
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.staff.schemas.clubs import ClubCreate, ClubUpdate, ClubRead, ClubListResponse
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.clubs import (
    get_club_by_id,
    get_clubs_by_owner,
    get_clubs_paginated,
    create_club,
    update_club,
    delete_club,
    check_user_club_permission,
    check_user_clubs_limit_before_create,
    get_user_clubs_with_roles,
)
from app.core.exceptions import ResourceNotFoundError, AuthorizationError

router = APIRouter(prefix="/clubs", tags=["Clubs"])


@router.get("/limits/check")
@limiter.limit("20/minute")
async def check_club_creation_limits(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Проверить лимиты на создание клубов для текущего пользователя.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем try/catch блок
    limits_info = await check_user_clubs_limit_before_create(db, user_staff.id)
    return limits_info


@router.post("/", response_model=ClubRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("3/minute")
async def create_new_club(
    request: Request,
    club: ClubCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new club. The authenticated user becomes the owner.
    """
    # Get user from database to ensure they exist as staff
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found. Please register as staff first.",
            error_code="STAFF_USER_NOT_FOUND",
        )

    # Убираем try/catch блок - exception handler справится
    db_club = await create_club(db, club, user_staff.id)
    return db_club


@router.get("/", response_model=ClubListResponse)
@limiter.limit("30/minute")
async def get_clubs_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(10, ge=1, le=50, description="Number of items per page"),
    city: Optional[str] = Query(None, description="Filter by city (partial match)"),
    name: Optional[str] = Query(
        None, description="Filter by club name (partial match)"
    ),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of all clubs with optional filters.

    - **page**: Page number (starts from 1)
    - **size**: Number of clubs per page (max 50)
    - **city**: Filter by city name (partial match)
    - **name**: Filter by club name (partial match)
    """
    skip = (page - 1) * size

    clubs, total = await get_clubs_paginated(
        db, skip=skip, limit=size, city=city, name=name
    )

    pages = math.ceil(total / size) if total > 0 else 1

    filters = {}
    if city:
        filters["city"] = city
    if name:
        filters["name"] = name

    return ClubListResponse(
        clubs=clubs,
        total=total,
        page=page,
        size=size,
        pages=pages,
        filters=filters if filters else None,
    )


@router.get("/my", response_model=List[ClubRead])
@limiter.limit("20/minute")
async def get_my_clubs(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    clubs = await get_clubs_by_owner(db, user_staff.id)
    return clubs


@router.get("/my/with-roles")
@limiter.limit("20/minute")
async def get_my_clubs_with_roles(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    clubs_with_roles = await get_user_clubs_with_roles(db, user_staff.id)
    return {
        "clubs": clubs_with_roles,
        "total": len(clubs_with_roles),
        "user_id": user_staff.id,
    }


@router.get("/{club_id}", response_model=ClubRead)
@limiter.limit("30/minute")
async def get_club(
    request: Request,
    club_id: int,
    db: AsyncSession = Depends(get_session),
):
    club = await get_club_by_id(db, club_id)
    if not club:
        raise ResourceNotFoundError("Club not found", error_code="CLUB_NOT_FOUND")
    return club


@router.put("/{club_id}", response_model=ClubRead)
@limiter.limit("10/minute")
async def update_club_details(
    request: Request,
    club_id: int,
    club_update: ClubUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update club details. Only club owner or admins can update.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    # Check if user has permission to update this club
    has_permission = await check_user_club_permission(db, user_staff.id, club_id)
    if not has_permission:
        from app.core.exceptions import AuthorizationError

        raise AuthorizationError(
            "You don't have permission to update this club",
            error_code="INSUFFICIENT_PERMISSIONS",
        )

    # Убираем try/catch блок - exception handler справится
    db_club = await update_club(db, club_id, club_update, user_staff.id)
    return db_club


@router.delete("/{club_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_club_route(
    request: Request,
    club_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Delete a club. Only club owner can delete.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    # Убираем try/catch блок - exception handler справится
    deleted = await delete_club(db, club_id, user_staff.id)


@router.get("/{club_id}/check-permission")
@limiter.limit("20/minute")
async def check_club_permission(
    request: Request,
    club_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise ResourceNotFoundError(
            "Staff user not found", error_code="STAFF_USER_NOT_FOUND"
        )

    club = await get_club_by_id(db, club_id)
    if not club:
        raise ResourceNotFoundError("Club not found", error_code="CLUB_NOT_FOUND")

    has_permission = await check_user_club_permission(db, user_staff.id, club_id)
    is_owner = club.owner_id == user_staff.id

    return {
        "club_id": club_id,
        "user_id": user_staff.id,
        "has_permission": has_permission,
        "is_owner": is_owner,
        "can_manage": has_permission,
        "can_delete": is_owner,
    }
