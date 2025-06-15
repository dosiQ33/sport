from typing import Optional
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.schemas.clubs import ClubCreate, ClubUpdate
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role, RoleType


async def get_club_by_id(session: AsyncSession, club_id: int):
    """Get club by ID with owner information"""
    result = await session.execute(
        select(Club).options(selectinload(Club.owner)).where(Club.id == club_id)
    )
    return result.scalar_one_or_none()


async def get_club_by_name(session: AsyncSession, name: str):
    """Get club by name"""
    result = await session.execute(select(Club).where(Club.name == name))
    return result.scalar_one_or_none()


async def get_clubs_by_owner(session: AsyncSession, owner_id: int):
    """Get all clubs owned by a specific user"""
    result = await session.execute(
        select(Club)
        .options(selectinload(Club.owner))
        .where(Club.owner_id == owner_id)
        .order_by(Club.created_at.desc())
    )
    return result.scalars().all()


async def get_clubs_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    city: Optional[str] = None,
    name: Optional[str] = None,
):
    """Get paginated list of clubs with optional filters"""
    base_query = select(Club).options(selectinload(Club.owner))
    count_query = select(func.count(Club.id))

    conditions = []

    if city:
        conditions.append(Club.city.ilike(f"%{city}%"))

    if name:
        conditions.append(Club.name.ilike(f"%{name}%"))

    if conditions:
        filter_condition = and_(*conditions)
        base_query = base_query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = base_query.offset(skip).limit(limit).order_by(Club.created_at.desc())
    result = await session.execute(query)
    clubs = result.scalars().all()

    return clubs, total


async def create_club(session: AsyncSession, club: ClubCreate, owner_id: int) -> Club:
    """Create a new club"""
    # Проверяем лимит клубов
    owner = await session.get(UserStaff, owner_id)
    if not owner:
        raise ValueError(f"Owner with ID {owner_id} not found")

    # # Проверяем лимит
    # if owner.clubs_limit > 0 and owner.clubs_created >= owner.clubs_limit:
    #     raise ValueError(
    #         f"You have reached your club creation limit ({owner.clubs_limit})"
    #     )

    # Существующая логика...
    existing_club = await get_club_by_name(session, club.name)
    if existing_club:
        raise ValueError(f"Club with name '{club.name}' already exists")

    club_data = club.model_dump()
    club_data["owner_id"] = owner_id

    try:
        db_club = Club(**club_data)
        session.add(db_club)
        await session.commit()
        await session.refresh(db_club)
        await session.refresh(db_club, ["owner"])

        return db_club
    except Exception as e:
        await session.rollback()
        raise


async def update_club(
    session: AsyncSession,
    club_id: int,
    club_update: ClubUpdate,
    owner_id: Optional[int] = None,
) -> Optional[Club]:
    """Update an existing club"""
    db_club = await get_club_by_id(session, club_id)
    if not db_club:
        return None

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise PermissionError("You can only update clubs you own")

    # Check if new name conflicts with existing clubs
    update_data = club_update.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_club.name:
        existing_club = await get_club_by_name(session, update_data["name"])
        if existing_club:
            raise ValueError(f"Club with name '{update_data['name']}' already exists")

    try:
        for key, value in update_data.items():
            setattr(db_club, key, value)

        await session.commit()
        await session.refresh(db_club)

        # Load owner relationship
        await session.refresh(db_club, ["owner"])

        return db_club
    except Exception as e:
        await session.rollback()
        raise


async def delete_club(
    session: AsyncSession, club_id: int, owner_id: Optional[int] = None
) -> bool:
    """Delete a club (soft delete by setting active=False if such field exists, or hard delete)"""
    db_club = await get_club_by_id(session, club_id)
    if not db_club:
        return False

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise PermissionError("You can only delete clubs you own")

    try:
        await session.delete(db_club)
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        raise


async def check_user_club_permission(
    session: AsyncSession, user_id: int, club_id: int
) -> bool:
    """Check if user has permission to manage a club (is owner or has admin role)"""
    # Check if user is owner
    club_result = await session.execute(
        select(Club).where(and_(Club.id == club_id, Club.owner_id == user_id))
    )
    club = club_result.scalar_one_or_none()

    if club:
        return True

    role_result = await session.execute(
        select(UserRole)
        .join(Role)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.club_id == club_id,
                UserRole.is_active == True,
                Role.code.in_([RoleType.admin, RoleType.owner]),
            )
        )
    )
    user_role = role_result.scalar_one_or_none()

    return user_role is not None
