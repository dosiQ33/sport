from typing import Any, Dict, Optional
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.staff.models.roles import Role, RoleType
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.user_roles import UserRole
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


async def check_user_sections_limit_before_create(
    session: AsyncSession, user_id: int, club_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Проверить лимиты пользователя на создание секций.

    Args:
        user_id: ID пользователя
        club_id: ID клуба (опционально, для подсчета секций в конкретном клубе)

    Returns:
        Dict с информацией о лимитах и возможности создания
    """
    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User with ID {user_id} not found")

    # Получаем текущее количество секций пользователя
    # Считаем секции только в клубах, которыми владеет пользователь
    sections_query = (
        select(func.count(Section.id))
        .join(Club, Section.club_id == Club.id)
        .where(Club.owner_id == user_id)
    )

    if club_id:
        # Если указан конкретный клуб, считаем только секции в нем
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


async def check_user_club_section_permission(
    session: AsyncSession, user_id: int, club_id: int
) -> Dict[str, Any]:
    """
    Проверить права пользователя на создание секций в конкретном клубе.

    Args:
        user_id: ID пользователя
        club_id: ID клуба

    Returns:
        Dict с информацией о правах пользователя
    """
    # Проверяем существование клуба
    club_result = await session.execute(select(Club).where(Club.id == club_id))
    club = club_result.scalar_one_or_none()
    if not club:
        raise ValueError(f"Club with ID {club_id} not found")

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

    # Определяем права
    # Секции могут создавать: owner, admin
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


async def check_user_can_create_section_in_club(
    session: AsyncSession, user_id: int, club_id: int
) -> Dict[str, Any]:
    """
    Комплексная проверка: может ли пользователь создать секцию в конкретном клубе.
    Проверяет и лимиты, и права доступа.

    Args:
        user_id: ID пользователя
        club_id: ID клуба

    Returns:
        Dict с полной информацией о возможности создания секции
    """
    try:
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

    except ValueError as e:
        return {
            "can_create": False,
            "reason": str(e),
            "permission_check": None,
            "limits_check": None,
        }


async def get_user_sections_stats(
    session: AsyncSession, user_id: int
) -> Dict[str, Any]:
    """
    Получить статистику по секциям пользователя.

    Args:
        user_id: ID пользователя

    Returns:
        Dict со статистикой
    """
    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise ValueError(f"User with ID {user_id} not found")

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


# Обновляем существующую функцию create_section
async def create_section(
    session: AsyncSession, section: SectionCreate, user_id: int
) -> Section:
    """Create a new section with comprehensive checks"""

    try:
        # 1. Комплексная проверка прав и лимитов
        check_result = await check_user_can_create_section_in_club(
            session, user_id, section.club_id
        )

        if not check_result["can_create"]:
            raise ValueError(check_result["reason"])

        # 2. Проверяем уникальность имени секции в клубе
        existing_section = await session.execute(
            select(Section).where(
                and_(Section.club_id == section.club_id, Section.name == section.name)
            )
        )
        if existing_section.scalar_one_or_none():
            raise ValueError(
                f"Section with name '{section.name}' already exists in this club"
            )

        # 3. Проверяем существование тренера (если указан)
        if section.coach_id:
            coach_result = await session.execute(
                select(UserStaff).where(UserStaff.id == section.coach_id)
            )
            coach = coach_result.scalar_one_or_none()
            if not coach:
                raise ValueError(f"Coach with ID {section.coach_id} not found")

        # 4. Создаем секцию
        section_data = section.model_dump()
        db_section = Section(**section_data)
        session.add(db_section)

        await session.commit()
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
