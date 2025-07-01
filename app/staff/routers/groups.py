from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError
from app.staff.schemas.groups import (
    GroupCreate,
    GroupUpdate,
    GroupRead,
    GroupListResponse,
)
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.groups import (
    get_group_by_id,
    get_groups_by_section,
    get_groups_by_coach,
    get_groups_paginated,
    create_group,
    update_group,
    delete_group,
    get_group_statistics,
    toggle_group_status,
)

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.post("/", response_model=GroupRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def create_new_group(
    request: Request,
    group: GroupCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a new group in a section.

    Automatically checks:
    - User permissions in the club (owner/admin)
    - Coach belongs to the same club as section
    - Group name uniqueness within section

    - **section_id**: ID of the section where group will be created
    - **name**: Group name (required, must be unique within section)
    - **description**: Group description (optional)
    - **schedule**: JSON object with schedule information
    - **price**: Price for this group (optional)
    - **capacity**: Maximum number of students (optional)
    - **level**: Skill level
    - **coach_id**: ID of the coach assigned to this group (optional, must be from same club)
    - **tags**: List of tags (e.g., ["morning", "kids"])
    - **active**: Whether group is active (default: true)
    """
    # Get user from database to ensure they exist as staff
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user", "Please register as staff first")

    # All business logic errors are handled in CRUD automatically
    db_group = await create_group(db, group, user_staff.id)
    return db_group


@router.get("/", response_model=List[GroupRead])
@limiter.limit("30/minute")
async def get_groups_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    section_id: Optional[int] = Query(None, description="Filter by section ID"),
    club_id: Optional[int] = Query(None, description="Filter by club ID"),
    coach_id: Optional[int] = Query(None, description="Filter by coach ID"),
    level: Optional[str] = Query(None, description="Filter by skill level"),
    name: Optional[str] = Query(
        None, description="Filter by group name (partial match)"
    ),
    active_only: bool = Query(True, description="Show only active groups"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of groups with optional filters.

    - **page**: Page number (starts from 1)
    - **size**: Number of groups per page (max 100)
    - **section_id**: Filter by specific section
    - **club_id**: Filter by specific club
    - **coach_id**: Filter by specific coach
    - **level**: Filter by skill level
    - **name**: Filter by group name (partial match)
    - **active_only**: Show only active groups (default: true)
    """
    skip = (page - 1) * size

    # Validation and errors are handled in CRUD
    groups, total = await get_groups_paginated(
        db,
        skip=skip,
        limit=size,
        section_id=section_id,
        club_id=club_id,
        coach_id=coach_id,
        level=level,
        active_only=active_only,
        name=name,
    )

    return groups


@router.get("/section/{section_id}", response_model=List[GroupRead])
@limiter.limit("30/minute")
async def get_section_groups(
    request: Request,
    section_id: int = Path(..., description="Section ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return"),
    active_only: bool = Query(True, description="Show only active groups"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all groups for a specific section.

    - **section_id**: ID of the section
    - **skip**: Number of groups to skip (for pagination)
    - **limit**: Maximum number of groups to return
    - **active_only**: Show only active groups
    """
    # Validation happens in CRUD
    groups = await get_groups_by_section(
        db, section_id, skip=skip, limit=limit, active_only=active_only
    )
    return groups


@router.get("/coach/{coach_id}", response_model=List[GroupRead])
@limiter.limit("30/minute")
async def get_coach_groups(
    request: Request,
    coach_id: int = Path(..., description="Coach ID"),
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=200, description="Number of items to return"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all groups coached by a specific user.

    - **coach_id**: ID of the coach
    - **skip**: Number of groups to skip (for pagination)
    - **limit**: Maximum number of groups to return
    """
    # Validation happens in CRUD
    groups = await get_groups_by_coach(db, coach_id, skip=skip, limit=limit)
    return groups


@router.get("/my", response_model=List[GroupRead])
@limiter.limit("20/minute")
async def get_my_groups(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all groups coached by the authenticated user.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    groups = await get_groups_by_coach(db, user_staff.id)
    return groups


@router.get("/{group_id}", response_model=GroupRead)
@limiter.limit("30/minute")
async def get_group(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get group details by ID.

    - **group_id**: Unique group identifier
    """
    # Validation and errors are handled in CRUD
    group = await get_group_by_id(db, group_id)
    return group


@router.put("/{group_id}", response_model=GroupRead)
@limiter.limit("10/minute")
async def update_group_details(
    request: Request,
    group_update: GroupUpdate,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update group details. Only club owner or admins can update.

    - **group_id**: Unique group identifier
    - All fields are optional in update
    - Coach must belong to the same club as the section
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # All permission checks and errors are handled in CRUD
    db_group = await update_group(db, group_id, group_update, user_staff.id)
    return db_group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_group_route(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Delete a group. Only club owner or admins can delete.

    - **group_id**: Unique group identifier

    ⚠️ **Warning**: This action is irreversible and will also delete all related data.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # All permission checks and errors are handled in CRUD
    await delete_group(db, group_id, user_staff.id)
    # FastAPI automatically returns 204 No Content


@router.patch("/{group_id}/toggle-status", response_model=GroupRead)
@limiter.limit("10/minute")
async def toggle_group_status_route(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Toggle group active status (activate/deactivate).

    - **group_id**: Unique group identifier

    This is useful for temporarily disabling groups without deleting them.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # All permission checks and errors are handled in CRUD
    db_group = await toggle_group_status(db, group_id, user_staff.id)
    return db_group


@router.get("/{group_id}/stats")
@limiter.limit("20/minute")
async def get_group_stats(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get group statistics including enrollment info.

    - **group_id**: Unique group identifier

    Returns detailed statistics about the group.
    """
    # Validation and errors are handled in CRUD
    stats = await get_group_statistics(db, group_id)
    return stats
