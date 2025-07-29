from typing import Optional
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    PermissionDeniedError,
)
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role, RoleType
from app.staff.schemas.groups import GroupCreate, GroupUpdate


@db_operation
async def get_group_by_id(session: AsyncSession, group_id: int):
    """Get group by ID with section and coach information"""
    if group_id <= 0:
        raise ValidationError("Group ID must be positive")

    result = await session.execute(
        select(Group)
        .options(selectinload(Group.section), selectinload(Group.coach))
        .where(Group.id == group_id)
    )
    group = result.scalar_one_or_none()

    if not group:
        raise NotFoundError("Group", str(group_id))

    return group


@db_operation
async def get_groups_by_section(
    session: AsyncSession,
    section_id: int,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
):
    """Get all groups for a specific section"""
    if section_id <= 0:
        raise ValidationError("Section ID must be positive")

    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200")

    base_query = (
        select(Group)
        .options(selectinload(Group.section), selectinload(Group.coach))
        .where(Group.section_id == section_id)
    )

    if active_only:
        base_query = base_query.where(Group.active == True)

    query = base_query.offset(skip).limit(limit).order_by(Group.created_at.desc())
    result = await session.execute(query)
    return result.scalars().all()


@db_operation
async def get_groups_by_coach(
    session: AsyncSession, coach_id: int, skip: int = 0, limit: int = 100
):
    """Get all groups coached by a specific user"""
    if coach_id <= 0:
        raise ValidationError("Coach ID must be positive")

    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200")

    query = (
        select(Group)
        .options(selectinload(Group.section), selectinload(Group.coach))
        .where(Group.coach_id == coach_id)
        .offset(skip)
        .limit(limit)
        .order_by(Group.created_at.desc())
    )
    result = await session.execute(query)
    return result.scalars().all()


@db_operation
async def get_groups_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    section_id: Optional[int] = None,
    club_id: Optional[int] = None,
    coach_id: Optional[int] = None,
    level: Optional[str] = None,
    active_only: bool = True,
    name: Optional[str] = None,
):
    """Get paginated list of groups with optional filters"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    base_query = select(Group).options(
        selectinload(Group.section), selectinload(Group.coach)
    )
    count_query = select(func.count(Group.id))

    conditions = []

    if section_id:
        if section_id <= 0:
            raise ValidationError("Section ID must be positive")
        conditions.append(Group.section_id == section_id)

    if club_id:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        # Join with Section to filter by club
        base_query = base_query.join(Section, Group.section_id == Section.id)
        count_query = count_query.join(Section, Group.section_id == Section.id)
        conditions.append(Section.club_id == club_id)

    if coach_id:
        if coach_id <= 0:
            raise ValidationError("Coach ID must be positive")
        conditions.append(Group.coach_id == coach_id)

    if level:
        conditions.append(Group.level == level.strip())

    if name:
        conditions.append(Group.name.ilike(f"%{name.strip()}%"))

    if active_only:
        conditions.append(Group.active == True)

    if conditions:
        filter_condition = and_(*conditions)
        base_query = base_query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = base_query.offset(skip).limit(limit).order_by(Group.created_at.desc())
    result = await session.execute(query)
    groups = result.scalars().all()

    return groups, total


@db_operation
async def validate_coach_is_club_member(
    session: AsyncSession, coach_id: int, club_id: int
) -> bool:
    """
    Проверить, что тренер является членом клуба (имеет активную роль)
    """
    if coach_id <= 0:
        raise ValidationError("Coach ID must be positive")

    if club_id <= 0:
        raise ValidationError("Club ID must be positive")

    # Проверяем, что coach существует
    coach_result = await session.execute(
        select(UserStaff).where(UserStaff.id == coach_id)
    )
    coach = coach_result.scalar_one_or_none()
    if not coach:
        raise NotFoundError("Coach", str(coach_id))

    # Проверяем, что coach имеет активную роль в этом клубе
    role_result = await session.execute(
        select(UserRole).where(
            and_(
                UserRole.user_id == coach_id,
                UserRole.club_id == club_id,
                UserRole.is_active == True,
            )
        )
    )
    user_role = role_result.scalar_one_or_none()

    if not user_role:
        raise ValidationError(
            f"Coach must be a member of the club. User {coach_id} has no active role in club {club_id}"
        )

    return True


async def create_group(
    session: AsyncSession, group: GroupCreate, user_id: int
) -> Group:
    """Create a new group with comprehensive checks"""

    async def _create_group_operation(session: AsyncSession):
        # 1. Verify section exists and get its club_id
        section_result = await session.execute(
            select(Section)
            .options(selectinload(Section.club))
            .where(Section.id == group.section_id)
        )
        section = section_result.scalar_one_or_none()
        if not section:
            raise NotFoundError("Section", str(group.section_id))

        club_id = section.club_id

        # 2. Check user has permission to create groups in this club
        from app.staff.crud.sections import check_user_club_section_permission

        permission_check = await check_user_club_section_permission(
            session, user_id, club_id
        )
        if not permission_check["can_create"]:
            raise PermissionDeniedError("create", "group", permission_check["reason"])

        # 3. Check group name uniqueness within section
        existing_group = await session.execute(
            select(Group).where(
                and_(
                    Group.section_id == group.section_id,
                    Group.name == group.name.strip(),
                )
            )
        )
        if existing_group.scalar_one_or_none():
            raise DuplicateError("Group", "name", f"{group.name} in this section")

        # 4. Validate coach if specified
        if group.coach_id:
            # Check coach exists
            coach_result = await session.execute(
                select(UserStaff).where(UserStaff.id == group.coach_id)
            )
            coach = coach_result.scalar_one_or_none()
            if not coach:
                raise NotFoundError("Coach", str(group.coach_id))

            # Validate coach belongs to the same club
            await validate_coach_is_club_member(session, group.coach_id, club_id)

        # 6. Create group
        group_data = group.model_dump()
        db_group = Group(**group_data)
        session.add(db_group)

        return db_group

    # Execute operation in transaction
    db_group = await with_db_transaction(session, _create_group_operation)

    # Load related data
    await session.refresh(db_group, ["section", "coach"])
    return db_group


@db_operation
async def update_group(
    session: AsyncSession,
    group_id: int,
    group_update: GroupUpdate,
    user_id: int,
) -> Group:
    """Update an existing group"""
    if group_id <= 0:
        raise ValidationError("Group ID must be positive")

    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Get group with section info
    group_result = await session.execute(
        select(Group)
        .options(selectinload(Group.section), selectinload(Group.coach))
        .where(Group.id == group_id)
    )
    db_group = group_result.scalar_one_or_none()

    if not db_group:
        raise NotFoundError("Group", str(group_id))

    club_id = db_group.section.club_id

    # FIXED: Direct permission check without problematic async function calls
    # Check if user is club owner
    club_result = await session.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()

    if not club:
        raise NotFoundError("Club", str(club_id))

    is_owner = club.owner_id == user_id

    # Check if user has admin/owner role in this club
    has_permission = False
    if not is_owner:
        user_role_result = await session.execute(
            select(UserRole, Role.code)
            .join(Role, UserRole.role_id == Role.id)
            .where(
                and_(
                    UserRole.user_id == user_id,
                    UserRole.club_id == club_id,
                    UserRole.is_active == True,
                )
            )
        )
        user_role_data = user_role_result.first()

        if user_role_data:
            role_code = user_role_data[1]  # Role.code
            has_permission = role_code in [RoleType.owner, RoleType.admin]

    if not (is_owner or has_permission):
        raise PermissionDeniedError(
            "update", "group", "No permission to update group in this club"
        )

    update_data = group_update.model_dump(exclude_unset=True)

    # FIXED: Inline coach validation without separate async function
    if "coach_id" in update_data and update_data["coach_id"]:
        if update_data["coach_id"] <= 0:
            raise ValidationError("Coach ID must be positive")

        # Check coach exists
        coach_result = await session.execute(
            select(UserStaff).where(UserStaff.id == update_data["coach_id"])
        )
        coach = coach_result.scalar_one_or_none()
        if not coach:
            raise NotFoundError("Coach", str(update_data["coach_id"]))

        await validate_coach_is_club_member(session, update_data["coach_id"], club_id)

    # Check name conflicts
    if "name" in update_data and update_data["name"] != db_group.name:
        existing_group = await session.execute(
            select(Group).where(
                and_(
                    Group.section_id == db_group.section_id,
                    Group.name == update_data["name"].strip(),
                    Group.id != group_id,
                )
            )
        )
        if existing_group.scalar_one_or_none():
            raise DuplicateError(
                "Group", "name", f"{update_data['name']} in this section"
            )

    # Apply changes
    for key, value in update_data.items():
        setattr(db_group, key, value)

    await session.commit()
    await session.refresh(db_group, ["section", "coach", "updated_at"])

    return db_group


@db_operation
async def delete_group(session: AsyncSession, group_id: int, user_id: int) -> bool:
    """Delete a group"""
    if group_id <= 0:
        raise ValidationError("Group ID must be positive")

    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Get group with section info
    group_result = await session.execute(
        select(Group).options(selectinload(Group.section)).where(Group.id == group_id)
    )
    db_group = group_result.scalar_one_or_none()

    if not db_group:
        raise NotFoundError("Group", str(group_id))

    club_id = db_group.section.club_id

    # Check permissions
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("delete", "group", permission_check["reason"])

    # Hard delete
    await session.delete(db_group)
    await session.commit()
    return True


@db_operation
async def get_group_statistics(session: AsyncSession, group_id: int):
    """Get statistics for a group"""
    if group_id <= 0:
        raise ValidationError("Group ID must be positive")

    group = await get_group_by_id(session, group_id)

    stats = {
        "id": group.id,
        "name": group.name,
        "section_name": group.section.name if group.section else None,
        "coach_name": (
            f"{group.coach.first_name} {group.coach.last_name or ''}".strip()
            if group.coach
            else None
        ),
        "capacity": group.capacity,
        "level": group.level,
        "active": group.active,
        "price": group.price,
        # Add more stats here when you implement student enrollment
        "enrolled_students": 0,  # Placeholder
        "available_spots": group.capacity if group.capacity else None,
    }

    return stats


@db_operation
async def toggle_group_status(
    session: AsyncSession, group_id: int, user_id: int
) -> Group:
    """Toggle group active status"""
    if group_id <= 0:
        raise ValidationError("Group ID must be positive")

    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Get group with section info
    group_result = await session.execute(
        select(Group)
        .options(selectinload(Group.section), selectinload(Group.coach))
        .where(Group.id == group_id)
    )
    db_group = group_result.scalar_one_or_none()

    if not db_group:
        raise NotFoundError("Group", str(group_id))

    club_id = db_group.section.club_id

    # Check permissions
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("modify", "group", permission_check["reason"])

    db_group.active = not db_group.active
    await session.commit()
    await session.refresh(db_group, ["section", "coach"])
    return db_group
