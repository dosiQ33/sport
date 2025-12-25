from typing import Any, Dict, List, Optional
from sqlalchemy import and_, func, delete
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    PermissionDeniedError,
    LimitExceededError,
)
from app.staff.models.roles import Role, RoleType
from app.staff.models.sections import Section
from app.staff.models.section_coaches import SectionCoach
from app.staff.models.groups import Group
from app.staff.models.clubs import Club
from app.staff.models.user_roles import UserRole
from app.staff.models.users import UserStaff
from app.staff.schemas.sections import SectionCreate, SectionUpdate


@db_operation
async def get_section_by_id(session: AsyncSession, section_id: int):
    """Get section by ID with club, coach, and groups information"""
    if not section_id or section_id <= 0:
        raise ValidationError("Section ID must be positive")

    result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.id == section_id)
    )
    section = result.scalar_one_or_none()

    if not section:
        raise NotFoundError("Section", str(section_id))

    # Pre-access all lazy relationships to ensure they're loaded in async context
    # This prevents greenlet errors when Pydantic validators access them synchronously
    _ = section.club
    _ = section.coach
    _ = section.groups
    for sc in section.section_coaches:
        _ = sc.coach  # Force load each coach relationship

    return section


@db_operation
async def get_sections_by_club(
    session: AsyncSession,
    club_id: int,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
):
    """Get all sections for a specific club"""
    if not club_id or club_id <= 0:
        raise ValidationError("Club ID must be positive")

    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200")

    base_query = (
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.club_id == club_id)
    )

    if active_only:
        base_query = base_query.where(Section.active == True)

    query = base_query.offset(skip).limit(limit).order_by(Section.created_at.desc())
    result = await session.execute(query)
    sections = result.scalars().all()
    
    # Pre-access all lazy relationships to prevent greenlet errors
    for section in sections:
        _ = section.club
        _ = section.coach
        _ = section.groups
        for sc in section.section_coaches:
            _ = sc.coach
    
    return sections


@db_operation
async def get_sections_by_coach(
    session: AsyncSession, coach_id: int, skip: int = 0, limit: int = 100
):
    """Get all sections coached by a specific user (primary or additional coach)"""
    if not coach_id or coach_id <= 0:
        raise ValidationError("Coach ID must be positive")

    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 200:
        raise ValidationError("Limit must be between 1 and 200")

    # First get distinct section IDs to avoid DISTINCT issues
    section_ids_subquery = (
        select(Section.id)
        .outerjoin(SectionCoach, Section.id == SectionCoach.section_id)
        .where(
            (Section.coach_id == coach_id) | 
            (
                (SectionCoach.coach_id == coach_id) & 
                (SectionCoach.is_active == True)
            )
        )
        .distinct()
        .subquery()
    )
    
    # Then fetch full section data for those IDs
    query = (
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.id.in_(select(section_ids_subquery.c.id)))
        .order_by(Section.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await session.execute(query)
    sections = result.scalars().all()
    
    # Pre-access all lazy relationships to prevent greenlet errors
    for section in sections:
        _ = section.club
        _ = section.coach
        _ = section.groups
        for sc in section.section_coaches:
            _ = sc.coach
    
    return sections


@db_operation
async def get_sections_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    club_id: Optional[int] = None,
    coach_id: Optional[int] = None,
    active_only: bool = True,
    name: Optional[str] = None,
    level: Optional[str] = None,
):
    """Get paginated list of sections with optional filters"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    base_query = select(Section).options(
        selectinload(Section.club),
        selectinload(Section.coach),
        selectinload(Section.groups),
        selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
    )
    count_query = select(func.count(Section.id))

    conditions = []

    if club_id:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        conditions.append(Section.club_id == club_id)

    if coach_id:
        if coach_id <= 0:
            raise ValidationError("Coach ID must be positive")
        conditions.append(Section.coach_id == coach_id)

    if name:
        conditions.append(Section.name.ilike(f"%{name.strip()}%"))

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

    # Pre-access all lazy relationships to prevent greenlet errors
    for section in sections:
        _ = section.club
        _ = section.coach
        _ = section.groups
        for sc in section.section_coaches:
            _ = sc.coach

    return sections, total


@db_operation
async def check_user_sections_limit_before_create(
    session: AsyncSession, user_id: int, club_id: Optional[int] = None
) -> Dict[str, Any]:
    """Проверить лимиты пользователя на создание секций"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise NotFoundError("Staff user", str(user_id))

    # Получаем текущее количество секций пользователя
    sections_query = (
        select(func.count(Section.id))
        .join(Club, Section.club_id == Club.id)
        .where(Club.owner_id == user_id)
    )

    if club_id:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        sections_query = sections_query.where(Club.id == club_id)

    current_sections_result = await session.execute(sections_query)
    current_sections_count = current_sections_result.scalar() or 0

    # Получаем лимиты пользователя
    user_limits = user.limits or {"clubs": 0, "sections": 0}
    max_sections = user_limits.get("sections", 0)

    can_create = current_sections_count < max_sections

    return {
        "can_create": can_create,
        "current_sections": current_sections_count,
        "max_sections": max_sections,
        "remaining": max_sections - current_sections_count if can_create else 0,
        "reason": (
            None
            if can_create
            else f"Limit reached: {current_sections_count}/{max_sections}"
        ),
        "club_id": club_id,
    }


@db_operation
async def check_user_club_section_permission(
    session: AsyncSession, user_id: int, club_id: int
) -> Dict[str, Any]:
    """Проверить права пользователя на создание секций в конкретном клубе"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    if not club_id or club_id <= 0:
        raise ValidationError("Club ID must be positive")

    # Проверяем существование клуба
    club_result = await session.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if not club:
        raise NotFoundError("Club", str(club_id))

    # Проверяем, является ли пользователь владельцем клуба
    is_owner = club.owner_id == user_id

    # Проверяем роли пользователя в клубе
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

    user_role = None
    if user_role_data:
        user_role = user_role_data[1].value  # Role code

    # Определяем права (секции могут создавать: owner, admin)
    can_create_sections = is_owner or user_role in [
        RoleType.owner.value,
        RoleType.admin.value,
    ]

    return {
        "can_create": can_create_sections,
        "is_owner": is_owner,
        "user_role": user_role,
        "club_id": club_id,
        "club_name": club.name,
        "reason": (
            None
            if can_create_sections
            else "No permission to create sections in this club"
        ),
    }


@db_operation
async def check_user_can_create_section_in_club(
    session: AsyncSession, user_id: int, club_id: int
) -> Dict[str, Any]:
    """Комплексная проверка: может ли пользователь создать секцию в конкретном клубе"""
    # 1. Проверяем права доступа к клубу
    permission_check = await check_user_club_section_permission(
        session, user_id, club_id
    )

    if not permission_check["can_create"]:
        return {
            "can_create": False,
            "reason": permission_check["reason"],
            "permission_check": permission_check,
            "limits_check": None,
        }

    # 2. Проверяем лимиты пользователя
    limits_check = await check_user_sections_limit_before_create(
        session, user_id, club_id
    )

    if not limits_check["can_create"]:
        return {
            "can_create": False,
            "reason": limits_check["reason"],
            "permission_check": permission_check,
            "limits_check": limits_check,
        }

    # 3. Все проверки пройдены
    return {
        "can_create": True,
        "reason": None,
        "permission_check": permission_check,
        "limits_check": limits_check,
    }


@db_operation
async def get_user_sections_stats(
    session: AsyncSession, user_id: int
) -> Dict[str, Any]:
    """Получить статистику по секциям пользователя"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise NotFoundError("Staff user", str(user_id))

    # Считаем секции по клубам пользователя
    sections_by_club_result = await session.execute(
        select(Club.id, Club.name, func.count(Section.id).label("sections_count"))
        .outerjoin(Section, Club.id == Section.club_id)
        .where(Club.owner_id == user_id)
        .group_by(Club.id, Club.name)
        .order_by(Club.name)
    )

    clubs_sections = []
    total_sections = 0

    for club_id, club_name, sections_count in sections_by_club_result:
        clubs_sections.append(
            {
                "club_id": club_id,
                "club_name": club_name,
                "sections_count": sections_count or 0,
            }
        )
        total_sections += sections_count or 0

    # Получаем лимиты
    user_limits = user.limits or {"clubs": 0, "sections": 0}
    max_sections = user_limits.get("sections", 0)

    return {
        "user_id": user_id,
        "total_sections": total_sections,
        "max_sections": max_sections,
        "remaining_sections": max_sections - total_sections,
        "clubs_sections": clubs_sections,
        "limits": user_limits,
    }


async def create_section(
    session: AsyncSession, section: SectionCreate, user_id: int
) -> Section:
    """Create a new section with comprehensive checks"""

    async def _create_section_operation(session: AsyncSession):
        # 1. Комплексная проверка прав и лимитов
        check_result = await check_user_can_create_section_in_club(
            session, user_id, section.club_id
        )

        if not check_result["can_create"]:
            if "limit" in check_result["reason"].lower() and check_result.get("limits_check"):
                limits_check = check_result["limits_check"]
                current = limits_check.get("current_sections", 0)
                max_limit = limits_check.get("max_sections", 0)
                raise LimitExceededError("sections", max_limit, current)
            else:
                raise PermissionDeniedError("create", "section", check_result["reason"])

        # 2. Проверяем уникальность имени секции в клубе
        existing_section = await session.execute(
            select(Section).where(
                and_(
                    Section.club_id == section.club_id,
                    Section.name == section.name.strip(),
                )
            )
        )
        if existing_section.scalar_one_or_none():
            raise DuplicateError("Section", "name", f"{section.name} in this club")

        # 3. Проверяем существование главного тренера
        if section.coach_id:
            await validate_coach_is_club_member(
                session, section.coach_id, section.club_id
            )

        # 4. Собираем всех тренеров
        all_coach_ids = set()
        all_coach_ids.add(section.coach_id)  # Primary coach
        if section.coach_ids:
            for coach_id in section.coach_ids:
                await validate_coach_is_club_member(session, coach_id, section.club_id)
                all_coach_ids.add(coach_id)

        # 5. Создаем секцию (без coach_ids поля, оно не в модели)
        section_data = section.model_dump(exclude={"coach_ids"})
        db_section = Section(**section_data)
        session.add(db_section)
        await session.flush()  # Get the section ID
        
        # 6. Создаем записи в section_coaches для всех тренеров
        for coach_id in all_coach_ids:
            section_coach = SectionCoach(
                section_id=db_section.id,
                coach_id=coach_id,
                is_primary=(coach_id == section.coach_id),
                is_active=True,
            )
            session.add(section_coach)

        return db_section

    # Выполняем операцию в транзакции
    db_section = await with_db_transaction(session, _create_section_operation)

    # Reload the section with all relationships properly loaded
    result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.id == db_section.id)
    )
    section = result.scalar_one()
    
    # Pre-access all lazy relationships to ensure they're loaded in async context
    # This prevents greenlet errors when Pydantic validators access them synchronously
    _ = section.club
    _ = section.coach
    _ = section.groups
    for sc in section.section_coaches:
        _ = sc.coach  # Force load each coach relationship
    
    return section


@db_operation
async def update_section(
    session: AsyncSession,
    section_id: int,
    section_update: SectionUpdate,
    user_id: int,
) -> Section:
    """Update an existing section"""
    if not section_id or section_id <= 0:
        raise ValidationError("Section ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем секцию
    section_result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches),
        )
        .where(Section.id == section_id)
    )
    db_section = section_result.scalar_one_or_none()

    if not db_section:
        raise NotFoundError("Section", str(section_id))

    # Проверяем права доступа
    permission_check = await check_user_club_section_permission(
        session, user_id, db_section.club_id
    )
    if not permission_check["can_create"]:  # can_create означает право управления
        raise PermissionDeniedError("update", "section", permission_check["reason"])

    update_data = section_update.model_dump(exclude_unset=True)
    
    # Extract coach_ids before processing other updates
    coach_ids = update_data.pop("coach_ids", None)

    # Verify primary coach exists if being updated
    if "coach_id" in update_data and update_data["coach_id"]:
        await validate_coach_is_club_member(
            session, update_data["coach_id"], db_section.club_id
        )

    # Check if new name conflicts with existing sections in the same club
    if "name" in update_data and update_data["name"] != db_section.name:
        existing_section = await session.execute(
            select(Section).where(
                and_(
                    Section.club_id == db_section.club_id,
                    Section.name == update_data["name"].strip(),
                    Section.id != section_id,
                )
            )
        )
        if existing_section.scalar_one_or_none():
            raise DuplicateError(
                "Section", "name", f"{update_data['name']} in this club"
            )

    # Применяем изменения к основным полям
    for key, value in update_data.items():
        setattr(db_section, key, value)
    
    # Обновляем список тренеров если передан coach_ids
    if coach_ids is not None:
        # Validate all coaches are club members
        for coach_id in coach_ids:
            await validate_coach_is_club_member(session, coach_id, db_section.club_id)
        
        # Удаляем старые записи section_coaches
        await session.execute(
            delete(SectionCoach).where(SectionCoach.section_id == section_id)
        )
        
        # Определяем primary coach
        primary_coach_id = update_data.get("coach_id") or db_section.coach_id
        
        # Создаем новые записи
        all_coach_ids = set(coach_ids)
        all_coach_ids.add(primary_coach_id)  # Ensure primary is included
        
        for coach_id in all_coach_ids:
            section_coach = SectionCoach(
                section_id=section_id,
                coach_id=coach_id,
                is_primary=(coach_id == primary_coach_id),
                is_active=True,
            )
            session.add(section_coach)

    await session.commit()
    
    # Reload the section with all relationships properly loaded (including nested)
    result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.id == section_id)
    )
    section = result.scalar_one()
    
    # Pre-access all lazy relationships to ensure they're loaded in async context
    _ = section.club
    _ = section.coach
    _ = section.groups
    for sc in section.section_coaches:
        _ = sc.coach
    
    return section


@db_operation
async def delete_section(session: AsyncSession, section_id: int, user_id: int) -> bool:
    """Delete a section (or deactivate it)"""
    if not section_id or section_id <= 0:
        raise ValidationError("Section ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем секцию
    section_result = await session.execute(
        select(Section).where(Section.id == section_id)
    )
    db_section = section_result.scalar_one_or_none()

    if not db_section:
        raise NotFoundError("Section", str(section_id))

    # Проверяем права доступа
    permission_check = await check_user_club_section_permission(
        session, user_id, db_section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("delete", "section", permission_check["reason"])

    # Hard delete (will cascade to groups)
    await session.delete(db_section)
    await session.commit()
    return True


@db_operation
async def get_section_statistics(session: AsyncSession, section_id: int):
    """Get statistics for a section"""
    if not section_id or section_id <= 0:
        raise ValidationError("Section ID must be positive")

    section = await get_section_by_id(session, section_id)

    # Count groups
    groups_count_result = await session.execute(
        select(func.count(Group.id)).where(Group.section_id == section_id)
    )
    total_groups = groups_count_result.scalar() or 0

    active_groups_result = await session.execute(
        select(func.count(Group.id)).where(
            and_(Group.section_id == section_id, Group.active == True)
        )
    )
    active_groups = active_groups_result.scalar() or 0

    # Calculate total capacity from active groups
    capacity_result = await session.execute(
        select(func.sum(Group.capacity)).where(
            and_(Group.section_id == section_id, Group.active == True)
        )
    )
    total_capacity = capacity_result.scalar()

    stats = {
        "id": section.id,
        "name": section.name,
        "coach_name": (
            f"{section.coach.first_name} {section.coach.last_name or ''}".strip()
            if section.coach
            else None
        ),
        "total_groups": total_groups,
        "active_groups": active_groups,
        "total_capacity": total_capacity,
        "active": section.active,
        # Add more stats here when you implement student enrollment
        "enrolled_students": 0,  # Placeholder
        "available_spots": total_capacity if total_capacity else None,
    }

    return stats


@db_operation
async def toggle_section_status(
    session: AsyncSession, section_id: int, user_id: int
) -> Section:
    """Toggle section active status"""
    if not section_id or section_id <= 0:
        raise ValidationError("Section ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем секцию
    section_result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
        )
        .where(Section.id == section_id)
    )
    db_section = section_result.scalar_one_or_none()

    if not db_section:
        raise NotFoundError("Section", str(section_id))

    # Проверяем права доступа
    permission_check = await check_user_club_section_permission(
        session, user_id, db_section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("modify", "section", permission_check["reason"])

    db_section.active = not db_section.active
    await session.commit()
    
    # Reload the section with all relationships properly loaded (including nested)
    result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.id == section_id)
    )
    section = result.scalar_one()
    
    # Pre-access all lazy relationships to ensure they're loaded in async context
    _ = section.club
    _ = section.coach
    _ = section.groups
    for sc in section.section_coaches:
        _ = sc.coach
    
    return section


@db_operation
async def get_sections_by_user_membership(
    session: AsyncSession, user_id: int
) -> List[Section]:
    """
    Get all sections from clubs where user has any role (owner, admin, coach)
    """
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем все клубы, где пользователь имеет любую роль
    user_clubs_result = await session.execute(
        select(UserRole.club_id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True,
            )
        )
        .distinct()
    )

    club_ids = [club_id for club_id, in user_clubs_result.fetchall()]

    if not club_ids:
        return []

    # Получаем все секции из этих клубов
    result = await session.execute(
        select(Section)
        .options(
            selectinload(Section.club),
            selectinload(Section.coach),
            selectinload(Section.groups),
            selectinload(Section.section_coaches).selectinload(SectionCoach.coach),
        )
        .where(Section.club_id.in_(club_ids))
        .order_by(Section.created_at.desc())
    )

    sections = result.scalars().all()
    
    # Pre-access all lazy relationships to prevent greenlet errors
    for section in sections:
        _ = section.club
        _ = section.coach
        _ = section.groups
        for sc in section.section_coaches:
            _ = sc.coach

    return sections


@db_operation
async def validate_coach_is_club_member(
    session: AsyncSession, coach_id: int, club_id: int
) -> bool:
    """
    Проверить, что тренер является членом клуба (имеет активную роль)
    """
    if not coach_id or coach_id <= 0:
        raise ValidationError("Coach ID must be positive")

    if not club_id or club_id <= 0:
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
