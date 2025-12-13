from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, func, cast, String

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.staff.models.tariffs import Tariff
from app.staff.models.user_roles import UserRole
from app.staff.schemas.tariffs import TariffCreate, TariffUpdate


async def get_tariff_by_id(db: AsyncSession, tariff_id: int) -> Tariff:
    """Get tariff by ID with creator info"""
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(Tariff.id == tariff_id)
    )
    tariff = result.scalar_one_or_none()

    if not tariff:
        raise NotFoundError("Tariff", f"Tariff with id {tariff_id} not found")

    return tariff


async def get_user_club_ids(db: AsyncSession, user_id: int) -> List[int]:
    """Get all club IDs where user has owner or admin role"""
    from app.staff.models.roles import RoleType, Role

    result = await db.execute(
        select(UserRole.club_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True,
                Role.code.in_([RoleType.owner, RoleType.admin]),
            )
        )
    )
    return [row[0] for row in result.fetchall()]


async def get_tariffs_by_user(
    db: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> List[Tariff]:
    """Get all tariffs for clubs where user is owner/admin"""
    # Get user's club IDs
    user_club_ids = await get_user_club_ids(db, user_id)

    if not user_club_ids:
        return []

    # Find tariffs that include any of user's clubs
    # Use PostgreSQL @> (contains) operator for JSON array containment
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(
            or_(
                # Check if any club_id in tariff.club_ids matches user's clubs
                # Cast JSON to text and use LIKE for compatibility
                *[cast(Tariff.club_ids, String).like(f'%{club_id}%') for club_id in user_club_ids]
            )
        )
        .order_by(Tariff.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    return list(result.scalars().all())


async def get_tariffs_paginated(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    club_id: Optional[int] = None,
    payment_type: Optional[str] = None,
    name: Optional[str] = None,
    active_only: bool = True,
) -> Tuple[List[Tariff], int]:
    """Get paginated list of tariffs with filters"""

    # Build query
    query = select(Tariff).options(selectinload(Tariff.created_by))
    count_query = select(func.count(Tariff.id))

    # Apply filters
    conditions = []

    if club_id:
        # Cast JSON to text and use LIKE for PostgreSQL compatibility
        conditions.append(cast(Tariff.club_ids, String).like(f'%{club_id}%'))
    
    if payment_type:
        conditions.append(Tariff.payment_type == payment_type)

    if name:
        conditions.append(Tariff.name.ilike(f"%{name}%"))

    if active_only:
        conditions.append(Tariff.active == True)

    if conditions:
        query = query.where(and_(*conditions))
        count_query = count_query.where(and_(*conditions))

    # Get total count
    count_result = await db.execute(count_query)
    total = count_result.scalar() or 0

    # Get tariffs
    query = query.order_by(Tariff.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    tariffs = list(result.scalars().all())

    return tariffs, total


async def create_tariff(
    db: AsyncSession, tariff_data: TariffCreate, user_id: int
) -> Tariff:
    """Create a new tariff"""

    # Validate that user has access to at least one of the specified clubs
    user_club_ids = await get_user_club_ids(db, user_id)

    if not user_club_ids:
        raise PermissionDeniedError(
            "create", "tariff", "You must be owner or admin of at least one club"
        )

    # Check that specified club_ids are in user's clubs
    if tariff_data.club_ids:
        invalid_clubs = set(tariff_data.club_ids) - set(user_club_ids)
        if invalid_clubs:
            raise PermissionDeniedError(
                "create",
                "tariff",
                f"You don't have permission for clubs: {invalid_clubs}",
            )

    # Validate session pack fields
    if tariff_data.payment_type == "session_pack":
        if not tariff_data.sessions_count:
            raise ValidationError("sessions_count is required for session pack tariffs")
        if not tariff_data.validity_days:
            raise ValidationError("validity_days is required for session pack tariffs")

    # Create tariff
    tariff = Tariff(
        name=tariff_data.name,
        description=tariff_data.description,
        type=tariff_data.type,
        payment_type=tariff_data.payment_type,
        price=tariff_data.price,
        club_ids=tariff_data.club_ids,
        section_ids=tariff_data.section_ids,
        group_ids=tariff_data.group_ids,
        sessions_count=tariff_data.sessions_count,
        validity_days=tariff_data.validity_days,
        active=tariff_data.active,
        created_by_id=user_id,
    )

    db.add(tariff)
    await db.commit()
    await db.refresh(tariff)

    # Load creator relationship
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(Tariff.id == tariff.id)
    )
    return result.scalar_one()


async def update_tariff(
    db: AsyncSession, tariff_id: int, tariff_data: TariffUpdate, user_id: int
) -> Tariff:
    """Update a tariff"""

    # Get existing tariff
    tariff = await get_tariff_by_id(db, tariff_id)

    # Check permission - user must have access to tariff's clubs
    user_club_ids = await get_user_club_ids(db, user_id)

    if not user_club_ids:
        raise PermissionDeniedError("update", "tariff")

    # Check if user has access to at least one of tariff's clubs
    tariff_clubs = set(tariff.club_ids or [])
    if not tariff_clubs.intersection(set(user_club_ids)):
        raise PermissionDeniedError(
            "update", "tariff", "You don't have access to this tariff"
        )

    # If updating club_ids, validate permissions
    if tariff_data.club_ids is not None:
        invalid_clubs = set(tariff_data.club_ids) - set(user_club_ids)
        if invalid_clubs:
            raise PermissionDeniedError(
                "update",
                "tariff",
                f"You don't have permission for clubs: {invalid_clubs}",
            )

    # Update fields
    update_data = tariff_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tariff, field, value)

    await db.commit()
    await db.refresh(tariff)

    # Reload with relationships
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(Tariff.id == tariff.id)
    )
    return result.scalar_one()


async def delete_tariff(db: AsyncSession, tariff_id: int, user_id: int) -> None:
    """Delete a tariff"""

    # Get tariff
    tariff = await get_tariff_by_id(db, tariff_id)

    # Check permission
    user_club_ids = await get_user_club_ids(db, user_id)

    if not user_club_ids:
        raise PermissionDeniedError("delete", "tariff")

    # Check if user has access to tariff's clubs
    tariff_clubs = set(tariff.club_ids or [])
    if not tariff_clubs.intersection(set(user_club_ids)):
        raise PermissionDeniedError(
            "delete", "tariff", "You don't have access to this tariff"
        )

    await db.delete(tariff)
    await db.commit()


async def toggle_tariff_status(
    db: AsyncSession, tariff_id: int, user_id: int
) -> Tariff:
    """Toggle tariff active status"""

    tariff = await get_tariff_by_id(db, tariff_id)

    # Check permission
    user_club_ids = await get_user_club_ids(db, user_id)

    if not user_club_ids:
        raise PermissionDeniedError("update", "tariff")

    tariff_clubs = set(tariff.club_ids or [])
    if not tariff_clubs.intersection(set(user_club_ids)):
        raise PermissionDeniedError(
            "update", "tariff", "You don't have access to this tariff"
        )

    tariff.active = not tariff.active
    await db.commit()
    await db.refresh(tariff)

    # Reload with relationships
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(Tariff.id == tariff.id)
    )
    return result.scalar_one()
