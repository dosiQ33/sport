from typing import Optional
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.roles import Role, RoleType
from app.staff.models.user_roles import UserRole
from app.staff.schemas.clubs import ClubCreate, ClubUpdate
from app.core.database import database_operation, retry_db_operation
from app.core.exceptions import (
    BusinessLogicError,
    ResourceNotFoundError,
    AuthorizationError,
)


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


@retry_db_operation(max_attempts=3)
@database_operation
async def create_club(session: AsyncSession, club: ClubCreate, owner_id: int) -> Club:
    """Create a new club with limits check and owner role assignment"""

    # 1. Проверяем лимиты пользователя
    limits_check = await check_user_clubs_limit_before_create(session, owner_id)

    if not limits_check["can_create"]:
        raise BusinessLogicError(
            f"User has reached the maximum limit of {limits_check['max_clubs']} clubs. "
            f"Current clubs: {limits_check['current_clubs']}. Contact administrator to increase limits.",
            error_code="CLUBS_LIMIT_EXCEEDED",
            details=limits_check,
        )

    # 2. Проверяем уникальность имени клуба
    existing_club = await get_club_by_name(session, club.name)
    if existing_club:
        raise BusinessLogicError(
            f"Club with name '{club.name}' already exists",
            error_code="CLUB_NAME_EXISTS",
        )

    # 3. Создаем клуб
    club_data = club.model_dump()
    club_data["owner_id"] = owner_id

    db_club = Club(**club_data)
    session.add(db_club)
    await session.flush()  # Получаем ID клуба

    # 4. Создаем owner роль для пользователя в этом клубе
    owner_role_result = await session.execute(
        select(Role).where(Role.code == RoleType.owner)
    )
    owner_role = owner_role_result.scalar_one()

    user_role = UserRole(
        user_id=owner_id,
        club_id=db_club.id,
        role_id=owner_role.id,
        is_active=True,
    )
    session.add(user_role)

    # 5. Применяем все изменения
    await session.commit()
    await session.refresh(db_club, ["owner"])

    return db_club


@database_operation
async def update_club(
    session: AsyncSession,
    club_id: int,
    club_update: ClubUpdate,
    owner_id: Optional[int] = None,
) -> Optional[Club]:
    """Update an existing club"""

    db_club = await get_club_by_id(session, club_id)
    if not db_club:
        raise ResourceNotFoundError(
            f"Club with ID {club_id} not found", error_code="CLUB_NOT_FOUND"
        )

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise AuthorizationError(
            "You can only update clubs you own", error_code="INSUFFICIENT_PERMISSIONS"
        )

    # Check if new name conflicts with existing clubs
    update_data = club_update.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_club.name:
        existing_club = await get_club_by_name(session, update_data["name"])
        if existing_club:
            raise BusinessLogicError(
                f"Club with name '{update_data['name']}' already exists",
                error_code="CLUB_NAME_EXISTS",
            )

    for key, value in update_data.items():
        setattr(db_club, key, value)

    await session.commit()
    await session.refresh(db_club, ["owner"])

    return db_club


@database_operation
async def delete_club(
    session: AsyncSession, club_id: int, owner_id: Optional[int] = None
) -> bool:
    """Delete a club (hard delete with cascading)"""

    db_club = await get_club_by_id(session, club_id)
    if not db_club:
        raise ResourceNotFoundError(
            f"Club with ID {club_id} not found", error_code="CLUB_NOT_FOUND"
        )

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise AuthorizationError(
            "You can only delete clubs you own", error_code="INSUFFICIENT_PERMISSIONS"
        )

    # Удаляем клуб (связанные записи удалятся автоматически из-за cascade)
    await session.delete(db_club)
    await session.commit()

    return True


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

    # Check if user has admin role in this club
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


async def get_user_clubs_with_roles(session: AsyncSession, user_id: int):
    """Get all clubs where user has any role"""
    result = await session.execute(
        select(Club, Role.code)
        .join(UserRole, Club.id == UserRole.club_id)
        .join(Role, UserRole.role_id == Role.id)
        .options(selectinload(Club.owner))
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True,
            )
        )
        .order_by(Club.created_at.desc())
    )

    clubs_with_roles = []
    for club, role_code in result:
        clubs_with_roles.append(
            {
                "club": club,
                "role": role_code.value,
                "is_owner": club.owner_id == user_id,
            }
        )

    return clubs_with_roles


async def check_user_clubs_limit_before_create(
    session: AsyncSession, user_id: int
) -> dict:
    """
    Проверить лимиты пользователя перед созданием клуба
    Возвращает информацию о возможности создания
    """
    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise ResourceNotFoundError(
            f"User with ID {user_id} not found", error_code="USER_NOT_FOUND"
        )

    # Получаем текущее количество клубов
    current_clubs_result = await session.execute(
        select(func.count(Club.id)).where(Club.owner_id == user_id)
    )
    current_clubs_count = current_clubs_result.scalar() or 0

    # Получаем лимиты
    user_limits = user.limits or {"clubs": 0, "sections": 0}
    max_clubs = user_limits.get("clubs", 0)

    can_create = current_clubs_count < max_clubs

    return {
        "can_create": can_create,
        "current_clubs": current_clubs_count,
        "max_clubs": max_clubs,
        "remaining": max_clubs - current_clubs_count if can_create else 0,
        "reason": (
            None if can_create else f"Limit reached: {current_clubs_count}/{max_clubs}"
        ),
    }
