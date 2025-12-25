from typing import List, Optional, Tuple, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import and_, or_, func, cast, String

from app.core.exceptions import NotFoundError, PermissionDeniedError, ValidationError
from app.staff.models.tariffs import Tariff
from app.staff.models.user_roles import UserRole
from app.staff.models.sections import Section
from app.staff.models.groups import Group
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
    from app.staff.models.roles import Role, RoleType
    
    result = await db.execute(
        select(UserRole.club_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True,
                or_(
                    Role.code == RoleType.owner,
                    Role.code == RoleType.admin
                )
            )
        )
    )
    return [row[0] for row in result.fetchall()]


async def get_club_ids_from_sections(db: AsyncSession, section_ids: List[int]) -> Set[int]:
    """Get club IDs for given section IDs"""
    if not section_ids:
        return set()
    
    result = await db.execute(
        select(Section.club_id).where(Section.id.in_(section_ids))
    )
    return {row[0] for row in result.fetchall()}


async def get_club_ids_from_groups(db: AsyncSession, group_ids: List[int]) -> Set[int]:
    """Get club IDs for given group IDs (via sections)"""
    if not group_ids:
        return set()
    
    result = await db.execute(
        select(Section.club_id)
        .join(Group, Group.section_id == Section.id)
        .where(Group.id.in_(group_ids))
    )
    return {row[0] for row in result.fetchall()}


async def validate_and_get_club_ids_for_tariff(
    db: AsyncSession,
    user_club_ids: List[int],
    club_ids: List[int],
    section_ids: List[int],
    group_ids: List[int],
) -> List[int]:
    """
    Validate that all specified clubs/sections/groups belong to user's clubs.
    Returns the complete list of club_ids (including those derived from sections/groups).
    """
    all_club_ids = set(club_ids or [])
    
    # Validate explicitly specified club_ids
    if club_ids:
        invalid_clubs = set(club_ids) - set(user_club_ids)
        if invalid_clubs:
            raise PermissionDeniedError(
                "create", "tariff",
                f"You don't have permission for clubs: {invalid_clubs}"
            )
    
    # Validate section_ids and get their club_ids
    if section_ids:
        section_club_ids = await get_club_ids_from_sections(db, section_ids)
        
        # Check if all sections exist
        result = await db.execute(
            select(func.count(Section.id)).where(Section.id.in_(section_ids))
        )
        found_count = result.scalar() or 0
        if found_count != len(section_ids):
            raise ValidationError("One or more section IDs are invalid")
        
        # Check permission
        invalid_section_clubs = section_club_ids - set(user_club_ids)
        if invalid_section_clubs:
            raise PermissionDeniedError(
                "create", "tariff",
                f"You don't have permission for sections in clubs: {invalid_section_clubs}"
            )
        
        all_club_ids.update(section_club_ids)
    
    # Validate group_ids and get their club_ids
    if group_ids:
        group_club_ids = await get_club_ids_from_groups(db, group_ids)
        
        # Check if all groups exist
        result = await db.execute(
            select(func.count(Group.id)).where(Group.id.in_(group_ids))
        )
        found_count = result.scalar() or 0
        if found_count != len(group_ids):
            raise ValidationError("One or more group IDs are invalid")
        
        # Check permission
        invalid_group_clubs = group_club_ids - set(user_club_ids)
        if invalid_group_clubs:
            raise PermissionDeniedError(
                "create", "tariff",
                f"You don't have permission for groups in clubs: {invalid_group_clubs}"
            )
        
        all_club_ids.update(group_club_ids)
    
    return list(all_club_ids)


def build_json_array_contains_conditions(column, values: List[int]):
    """
    Build SQL conditions to check if a JSON array column contains any of the given values.
    Uses multiple patterns to handle JSON array format: [1, 2, 3]
    """
    conditions = []
    for val in values:
        # Match patterns in JSON array: [val], [val, ...], [..., val], [..., val, ...]
        conditions.extend([
            cast(column, String).like(f'%[{val}]%'),      # Single element: [4]
            cast(column, String).like(f'%[{val},%'),      # First element: [4, ...]
            cast(column, String).like(f'%, {val}]%'),     # Last element: [..., 4]
            cast(column, String).like(f'%, {val},%'),     # Middle element: [..., 4, ...]
        ])
    return conditions


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
    # Build precise JSON array containment conditions
    conditions = build_json_array_contains_conditions(Tariff.club_ids, user_club_ids)
    
    result = await db.execute(
        select(Tariff)
        .options(selectinload(Tariff.created_by))
        .where(or_(*conditions))
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
        # Use precise JSON array containment check
        club_conditions = build_json_array_contains_conditions(Tariff.club_ids, [club_id])
        conditions.append(or_(*club_conditions))
    
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
    db: AsyncSession, 
    tariff_data: TariffCreate, 
    user_id: int
) -> Tariff:
    """Create a new tariff"""
    
    # Validate that user has access to at least one of the specified clubs
    user_club_ids = await get_user_club_ids(db, user_id)
    
    if not user_club_ids:
        raise PermissionDeniedError("create", "tariff", "You must be owner or admin of at least one club")
    
    # Validate all clubs/sections/groups belong to user and get complete club_ids list
    # This also auto-populates club_ids based on sections and groups
    complete_club_ids = await validate_and_get_club_ids_for_tariff(
        db,
        user_club_ids,
        tariff_data.club_ids or [],
        tariff_data.section_ids or [],
        tariff_data.group_ids or [],
    )
    
    # Ensure at least one club is associated
    if not complete_club_ids:
        raise ValidationError("Tariff must be associated with at least one club, section, or group")
    
    # Validate session pack fields
    if tariff_data.payment_type == "session_pack":
        if not tariff_data.sessions_count:
            raise ValidationError("sessions_count is required for session pack tariffs")
        if not tariff_data.validity_days:
            raise ValidationError("validity_days is required for session pack tariffs")
    
    # Create tariff with auto-populated club_ids
    tariff = Tariff(
        name=tariff_data.name,
        description=tariff_data.description,
        type=tariff_data.type,
        payment_type=tariff_data.payment_type,
        price=tariff_data.price,
        club_ids=complete_club_ids,  # Use the complete list including derived club_ids
        section_ids=tariff_data.section_ids or [],
        group_ids=tariff_data.group_ids or [],
        sessions_count=tariff_data.sessions_count,
        validity_days=tariff_data.validity_days,
        freeze_days_total=tariff_data.freeze_days_total,
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
    db: AsyncSession,
    tariff_id: int,
    tariff_data: TariffUpdate,
    user_id: int
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
        raise PermissionDeniedError("update", "tariff", "You don't have access to this tariff")
    
    update_data = tariff_data.model_dump(exclude_unset=True)
    
    # If updating club_ids, section_ids, or group_ids, validate and recalculate club_ids
    new_club_ids = update_data.get('club_ids', tariff.club_ids or [])
    new_section_ids = update_data.get('section_ids', tariff.section_ids or [])
    new_group_ids = update_data.get('group_ids', tariff.group_ids or [])
    
    # Only re-validate if any of these fields are being updated
    if 'club_ids' in update_data or 'section_ids' in update_data or 'group_ids' in update_data:
        complete_club_ids = await validate_and_get_club_ids_for_tariff(
            db,
            user_club_ids,
            new_club_ids if isinstance(new_club_ids, list) else [],
            new_section_ids if isinstance(new_section_ids, list) else [],
            new_group_ids if isinstance(new_group_ids, list) else [],
        )
        
        if not complete_club_ids:
            raise ValidationError("Tariff must be associated with at least one club, section, or group")
        
        # Update club_ids with the complete list
        update_data['club_ids'] = complete_club_ids
    
    # Update fields
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
        raise PermissionDeniedError("delete", "tariff", "You don't have access to this tariff")
    
    await db.delete(tariff)
    await db.commit()


async def toggle_tariff_status(db: AsyncSession, tariff_id: int, user_id: int) -> Tariff:
    """Toggle tariff active status"""
    
    tariff = await get_tariff_by_id(db, tariff_id)
    
    # Check permission
    user_club_ids = await get_user_club_ids(db, user_id)
    
    if not user_club_ids:
        raise PermissionDeniedError("update", "tariff")
    
    tariff_clubs = set(tariff.club_ids or [])
    if not tariff_clubs.intersection(set(user_club_ids)):
        raise PermissionDeniedError("update", "tariff", "You don't have access to this tariff")
    
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
