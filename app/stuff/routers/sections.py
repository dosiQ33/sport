from fastapi import APIRouter, Depends, HTTPException, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.stuff.schemas.sections import SectionCreate, SectionUpdate, SectionRead
from app.stuff.crud.users import get_user_stuff_by_telegram_id
from app.stuff.crud.sections import (
    get_section_by_id,
    get_sections_by_club,
    get_sections_by_coach,
    get_sections_paginated,
    create_section,
    update_section,
    delete_section,
    get_section_statistics,
    toggle_section_status,
)

router = APIRouter(prefix="/sections", tags=["Sections"])


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

    Only club owners and admins can create sections.
    """
    # Get user from database to ensure they exist as staff
    user_stuff = await get_user_stuff_by_telegram_id(db, current_user.get("id"))
    if not user_stuff:
        raise HTTPException(
            status_code=404,
            detail="Staff user not found. Please register as staff first.",
        )

    try:
        db_section = await create_section(db, section, user_stuff.id)
        return db_section
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to create section")


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
    """
    Get all sections coached by the authenticated user.
    """
    user_stuff = await get_user_stuff_by_telegram_id(db, current_user.get("id"))
    if not user_stuff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    sections = await get_sections_by_coach(db, user_stuff.id)
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
    section = await get_section_by_id(db, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
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
    user_stuff = await get_user_stuff_by_telegram_id(db, current_user.get("id"))
    if not user_stuff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    try:
        db_section = await update_section(db, section_id, section_update, user_stuff.id)
        if not db_section:
            raise HTTPException(status_code=404, detail="Section not found")
        return db_section
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update section")


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
    user_stuff = await get_user_stuff_by_telegram_id(db, current_user.get("id"))
    if not user_stuff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    try:
        deleted = await delete_section(db, section_id, user_stuff.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Section not found")
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to delete section")


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
    user_stuff = await get_user_stuff_by_telegram_id(db, current_user.get("id"))
    if not user_stuff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    try:
        db_section = await toggle_section_status(db, section_id, user_stuff.id)
        if not db_section:
            raise HTTPException(status_code=404, detail="Section not found")
        return db_section
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to toggle section status")


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
    stats = await get_section_statistics(db, section_id)
    if not stats:
        raise HTTPException(status_code=404, detail="Section not found")
    return stats
