from typing import Optional
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.schemas.sections import SectionCreate, SectionUpdate
from app.staff.crud.clubs import check_user_club_permission
from app.staff.crud.clubs import check_user_club_permission


async def get_section_by_id(session: AsyncSession, section_id: int):
    """Get section by ID with club and coach information"""
    result = await session.execute(
        select(Section)
        .options(selectinload(Section.club), selectinload(Section.coach))
        .where(Section.id == section_id)
    )
    return result.scalar_one_or_none()


async def get_sections_by_club(
    session: AsyncSession,
    club_id: int,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
):
    """Get all sections for a specific club"""
    base_query = (
        select(Section)
        .options(selectinload(Section.club), selectinload(Section.coach))
        .where(Section.club_id == club_id)
    )

    if active_only:
        base_query = base_query.where(Section.active == True)

    query = base_query.offset(skip).limit(limit).order_by(Section.created_at.desc())
    result = await session.execute(query)
    return result.scalars().all()


async def get_sections_by_coach(
    session: AsyncSession, coach_id: int, skip: int = 0, limit: int = 100
):
    """Get all sections coached by a specific user"""
    query = (
        select(Section)
        .options(selectinload(Section.club), selectinload(Section.coach))
        .where(Section.coach_id == coach_id)
        .offset(skip)
        .limit(limit)
        .order_by(Section.created_at.desc())
    )
    result = await session.execute(query)
    return result.scalars().all()


async def get_sections_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    club_id: Optional[int] = None,
    coach_id: Optional[int] = None,
    level: Optional[str] = None,
    active_only: bool = True,
    name: Optional[str] = None,
):
    """Get paginated list of sections with optional filters"""
    base_query = select(Section).options(
        selectinload(Section.club), selectinload(Section.coach)
    )
    count_query = select(func.count(Section.id))

    conditions = []

    if club_id:
        conditions.append(Section.club_id == club_id)

    if coach_id:
        conditions.append(Section.coach_id == coach_id)

    if level:
        conditions.append(Section.level == level)

    if name:
        conditions.append(Section.name.ilike(f"%{name}%"))

    if active_only:
        conditions.append(Section.active == True)

    if conditions:
        filter_condition = and_(*conditions)
        base_query = base_query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = base_query.offset(skip).limit(limit).order_by(Section.created_at.desc())
    result = await session.execute(query)
    sections = result.scalars().all()

    return sections, total


async def create_section(
    session: AsyncSession, section: SectionCreate, user_id: int
) -> Section:
    """Create a new section"""

    # Verify club exists and user has permission
    club_result = await session.execute(select(Club).where(Club.id == section.club_id))
    club = club_result.scalar_one_or_none()
    if not club:
        raise ValueError(f"Club with ID {section.club_id} not found")

    has_permission = await check_user_club_permission(session, user_id, section.club_id)
    if not has_permission:
        raise PermissionError(
            "You don't have permission to create sections in this club"
        )

    # Verify coach exists if provided
    if section.coach_id:
        coach_result = await session.execute(
            select(UserStaff).where(UserStaff.id == section.coach_id)
        )
        coach = coach_result.scalar_one_or_none()
        if not coach:
            raise ValueError(f"Coach with ID {section.coach_id} not found")

    # Check if section name is unique within the club
    existing_section = await session.execute(
        select(Section).where(
            and_(Section.club_id == section.club_id, Section.name == section.name)
        )
    )
    if existing_section.scalar_one_or_none():
        raise ValueError(
            f"Section with name '{section.name}' already exists in this club"
        )

    try:
        section_data = section.model_dump()
        db_section = Section(**section_data)
        session.add(db_section)
        await session.commit()
        await session.refresh(db_section)

        # Load relationships
        await session.refresh(db_section, ["club", "coach"])

        return db_section
    except Exception as e:
        await session.rollback()
        raise


async def update_section(
    session: AsyncSession,
    section_id: int,
    section_update: SectionUpdate,
    user_id: int,
) -> Optional[Section]:
    """Update an existing section"""
    db_section = await get_section_by_id(session, section_id)
    if not db_section:
        return None

    has_permission = await check_user_club_permission(
        session, user_id, db_section.club_id
    )
    if not has_permission:
        raise PermissionError(
            "You don't have permission to update sections in this club"
        )

    update_data = section_update.model_dump(exclude_unset=True)

    # Verify coach exists if being updated
    if "coach_id" in update_data and update_data["coach_id"]:
        coach_result = await session.execute(
            select(UserStaff).where(UserStaff.id == update_data["coach_id"])
        )
        coach = coach_result.scalar_one_or_none()
        if not coach:
            raise ValueError(f"Coach with ID {update_data['coach_id']} not found")

    # Check if new name conflicts with existing sections in the same club
    if "name" in update_data and update_data["name"] != db_section.name:
        existing_section = await session.execute(
            select(Section).where(
                and_(
                    Section.club_id == db_section.club_id,
                    Section.name == update_data["name"],
                    Section.id != section_id,
                )
            )
        )
        if existing_section.scalar_one_or_none():
            raise ValueError(
                f"Section with name '{update_data['name']}' already exists in this club"
            )

    try:
        for key, value in update_data.items():
            setattr(db_section, key, value)

        await session.commit()
        await session.refresh(db_section)

        # Load relationships
        await session.refresh(db_section, ["club", "coach"])

        return db_section
    except Exception as e:
        await session.rollback()
        raise


async def delete_section(session: AsyncSession, section_id: int, user_id: int) -> bool:
    """Delete a section (or deactivate it)"""
    db_section = await get_section_by_id(session, section_id)
    if not db_section:
        return False

    has_permission = await check_user_club_permission(
        session, user_id, db_section.club_id
    )
    if not has_permission:
        raise PermissionError(
            "You don't have permission to delete sections in this club"
        )

    try:
        # You can choose to either hard delete or soft delete (set active=False)
        # For soft delete:
        # db_section.active = False

        # For hard delete:
        await session.delete(db_section)
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        raise


async def get_section_statistics(session: AsyncSession, section_id: int):
    """Get statistics for a section (can be extended with student count, etc.)"""
    section = await get_section_by_id(session, section_id)
    if not section:
        return None

    # Basic stats - can be extended when you add student enrollment
    stats = {
        "id": section.id,
        "name": section.name,
        "club_name": section.club.name if section.club else None,
        "coach_name": (
            f"{section.coach.first_name} {section.coach.last_name}"
            if section.coach
            else None
        ),
        "capacity": section.capacity,
        "level": section.level,
        "active": section.active,
        "price": section.price,
        "duration_min": section.duration_min,
        # Add more stats here when you implement student enrollment
        "enrolled_students": 0,  # Placeholder
        "available_spots": section.capacity if section.capacity else None,
    }

    return stats


async def toggle_section_status(
    session: AsyncSession, section_id: int, user_id: int
) -> Optional[Section]:
    """Toggle section active status"""
    db_section = await get_section_by_id(session, section_id)
    if not db_section:
        return None

    has_permission = await check_user_club_permission(
        session, user_id, db_section.club_id
    )
    if not has_permission:
        raise PermissionError(
            "You don't have permission to modify sections in this club"
        )

    try:
        db_section.active = not db_section.active
        await session.commit()
        await session.refresh(db_section)
        await session.refresh(db_section, ["club", "coach"])
        return db_section
    except Exception as e:
        await session.rollback()
        raise
