import math
from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_staff_user
from app.core.exceptions import NotFoundError
from app.staff.schemas.tariffs import (
    TariffCreate,
    TariffUpdate,
    TariffRead,
    TariffListResponse,
)
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.tariffs import (
    get_tariff_by_id,
    get_tariffs_by_user,
    get_tariffs_paginated,
    create_tariff,
    update_tariff,
    delete_tariff,
    toggle_tariff_status,
)

router = APIRouter(prefix="/tariffs", tags=["Tariffs"])


@router.post("/", response_model=TariffRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_new_tariff(
    request: Request,
    tariff: TariffCreate,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new tariff/pricing plan.

    Only club owners and admins can create tariffs for their clubs.

    - **name**: Tariff name (required)
    - **description**: Description (optional)
    - **type**: Package type (full_club, full_section, single_group, multiple_groups)
    - **payment_type**: Payment frequency (monthly, semi_annual, annual, session_pack)
    - **price**: Price in KZT (required)
    - **club_ids**: List of club IDs this tariff applies to
    - **section_ids**: List of section IDs (for section/group level access)
    - **group_ids**: List of group IDs (for group level access)
    - **sessions_count**: Number of sessions (required for session_pack)
    - **validity_days**: Days the pack is valid (required for session_pack)
    - **active**: Whether tariff is active (default: true)
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    db_tariff = await create_tariff(db, tariff, user_staff.id)
    return db_tariff


@router.get("/", response_model=TariffListResponse)
@limiter.limit("30/minute")
async def get_tariffs_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    club_id: Optional[int] = Query(None, gt=0, description="Filter by club ID"),
    payment_type: Optional[str] = Query(None, description="Filter by payment type"),
    name: Optional[str] = Query(None, description="Filter by name (partial match)"),
    active_only: bool = Query(True, description="Show only active tariffs"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of tariffs with optional filters.

    - **page**: Page number (starts from 1)
    - **size**: Number of tariffs per page (max 100)
    - **club_id**: Filter by specific club
    - **payment_type**: Filter by payment type
    - **name**: Filter by tariff name (partial match)
    - **active_only**: Show only active tariffs (default: true)
    """
    skip = (page - 1) * size

    tariffs, total = await get_tariffs_paginated(
        db,
        skip=skip,
        limit=size,
        club_id=club_id,
        payment_type=payment_type,
        name=name,
        active_only=active_only,
    )

    pages = math.ceil(total / size) if total > 0 else 1

    # Build filters info
    filters = {}
    if club_id:
        filters["club_id"] = club_id
    if payment_type:
        filters["payment_type"] = payment_type
    if name:
        filters["name"] = name
    if not active_only:
        filters["active_only"] = active_only

    return TariffListResponse(
        tariffs=tariffs,
        total=total,
        page=page,
        size=size,
        pages=pages,
        filters=filters if filters else None,
    )


@router.get("/my", response_model=List[TariffRead])
@limiter.limit("30/minute")
async def get_my_tariffs(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all tariffs for clubs where current user is owner or admin.

    Returns tariffs that the authenticated user can manage.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    tariffs = await get_tariffs_by_user(db, user_staff.id)
    return tariffs


@router.get("/{tariff_id}", response_model=TariffRead)
@limiter.limit("30/minute")
async def get_tariff(
    request: Request,
    tariff_id: int = Path(..., description="Tariff ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get tariff details by ID.

    - **tariff_id**: Unique tariff identifier
    """
    tariff = await get_tariff_by_id(db, tariff_id)
    return tariff


@router.put("/{tariff_id}", response_model=TariffRead)
@limiter.limit("10/minute")
async def update_tariff_details(
    request: Request,
    tariff_update: TariffUpdate,
    tariff_id: int = Path(..., description="Tariff ID"),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update tariff details.

    Only club owners and admins can update tariffs for their clubs.

    - **tariff_id**: Unique tariff identifier
    - All fields are optional in update
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_tariff = await update_tariff(db, tariff_id, tariff_update, user_staff.id)
    return db_tariff


@router.delete("/{tariff_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_tariff_route(
    request: Request,
    tariff_id: int = Path(..., description="Tariff ID"),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Delete a tariff.

    Only club owners and admins can delete tariffs for their clubs.

    - **tariff_id**: Unique tariff identifier

    ⚠️ **Warning**: This action is irreversible.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    await delete_tariff(db, tariff_id, user_staff.id)


@router.patch("/{tariff_id}/toggle-status", response_model=TariffRead)
@limiter.limit("10/minute")
async def toggle_tariff_status_route(
    request: Request,
    tariff_id: int = Path(..., description="Tariff ID"),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Toggle tariff active status (activate/deactivate).

    - **tariff_id**: Unique tariff identifier

    Useful for temporarily disabling tariffs without deleting them.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_tariff = await toggle_tariff_status(db, tariff_id, user_staff.id)
    return db_tariff
