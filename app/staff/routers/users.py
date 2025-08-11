import math
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_staff_user
from app.core.exceptions import NotFoundError, DuplicateError
from app.staff.schemas.users import (
    UserStaffCreate,
    UserStaffUpdate,
    UserStaffRead,
    UserStaffListResponse,
    UserStaffPreferencesUpdate,
    UserStaffFilters,
)

from app.staff.crud.users import (
    get_user_staff_by_id,
    get_user_staff_by_telegram_id,
    get_users_staff_paginated,
    create_user_staff,
    update_user_staff,
    update_user_staff_preferences,
    get_user_staff_preference,
)

router = APIRouter(prefix="/staff", tags=["Staff"])


@router.post("/", response_model=UserStaffRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_new_user_staff(
    request: Request,
    user: UserStaffCreate,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new staff user.

    Requires valid Telegram authentication and an active invitation for the phone number.
    The system will automatically assign roles based on available invitations.
    """
    # Проверяем существование пользователя
    existing = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if existing:
        raise DuplicateError("Staff user", "telegram_id", str(current_user.get("id")))

    # Все остальные проверки и ошибки обрабатываются в CRUD
    return await create_user_staff(db, user, current_user)


@router.get("/me", response_model=UserStaffRead)
@limiter.limit("60/minute")
async def get_current_user_staff(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get current authenticated staff user profile.

    Returns the profile information of the currently authenticated staff user
    based on the Telegram authentication token.
    """
    user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user:
        raise NotFoundError("Staff user", "Please register as staff first")

    return user


@router.get("/{user_id}", response_model=UserStaffRead)
@limiter.limit("30/minute")
async def get_user_staff(
    request: Request, user_id: int, db: AsyncSession = Depends(get_session)
):
    """
    Get staff user by ID.

    - **user_id**: Unique staff user identifier
    """
    # Валидация и ошибки обрабатываются в CRUD
    user = await get_user_staff_by_id(db, user_id)
    return user


@router.get("/", response_model=UserStaffListResponse)
@limiter.limit("20/minute")
async def get_users_staff_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(10, ge=1, le=100, description="Number of items per page"),
    # Фильтры как query параметры
    first_name: Optional[str] = Query(
        None, description="Filter by first name (partial match)"
    ),
    last_name: Optional[str] = Query(
        None, description="Filter by last name (partial match)"
    ),
    phone_number: Optional[str] = Query(
        None, description="Filter by phone number (partial match)"
    ),
    username: Optional[str] = Query(
        None, description="Filter by username (partial match)"
    ),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of staff users with optional filters.

    - **page**: Page number (starts from 1)
    - **size**: Number of users per page (max 100)
    - **first_name**: Filter by first name (partial match)
    - **last_name**: Filter by last name (partial match)
    - **phone_number**: Filter by phone number (partial match)
    - **username**: Filter by username (partial match)
    """
    skip = (page - 1) * size

    # Создаем объект фильтров
    filters = UserStaffFilters(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number,
        username=username,
    )

    # Если все фильтры пустые, передаем None
    if not any([first_name, last_name, phone_number, username]):
        filters = None

    # Валидация параметров происходит в CRUD
    users, total = await get_users_staff_paginated(
        db, skip=skip, limit=size, filters=filters
    )

    pages = math.ceil(total / size) if total > 0 else 1

    return UserStaffListResponse(
        users=users, total=total, page=page, size=size, pages=pages, filters=filters
    )


@router.put("/me", response_model=UserStaffRead)
@limiter.limit("10/minute")
async def update_user_staff_by_telegram_id(
    request: Request,
    user: UserStaffUpdate,
    db: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
):
    """
    Update current staff user profile.

    - All fields are optional in update
    - Only the authenticated user can update their own profile
    """
    # Ошибки обрабатываются в CRUD
    db_user = await update_user_staff(db, current_user.get("id"), user)
    return db_user


@router.put("/preferences", response_model=UserStaffRead)
@limiter.limit("10/minute")
async def update_user_staff_preferences_route(
    request: Request,
    preferences: UserStaffPreferencesUpdate,
    db: AsyncSession = Depends(get_session),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
):
    """
    Update user staff preferences (language, dark_mode, notifications).

    - **language**: Language code (ru, en, kz, uz, ky)
    - **dark_mode**: Enable/disable dark mode
    - **notifications**: Enable/disable notifications
    """
    # Ошибки обрабатываются в CRUD
    db_user = await update_user_staff_preferences(
        db, preferences, current_user.get("id")
    )
    return db_user


@router.get("/{telegram_id}/preferences/{preference_key}")
@limiter.limit("10/minute")
async def get_user_staff_preference_route(
    request: Request,
    telegram_id: int,
    preference_key: str,
    db: AsyncSession = Depends(get_session),
):
    """
    Get specific user staff preference by key.

    - **telegram_id**: User's Telegram ID
    - **preference_key**: Preference key to retrieve
    """
    # Валидация и ошибки обрабатываются в CRUD
    preference_value = await get_user_staff_preference(db, telegram_id, preference_key)

    return {
        "telegram_id": telegram_id,
        "preference_key": preference_key,
        "value": preference_value,
    }
