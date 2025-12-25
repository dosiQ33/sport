from typing import Optional
from sqlalchemy import and_, func, text
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    LimitExceededError,
    PermissionDeniedError,
    ValidationError,
    DatabaseError,
)
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.roles import Role, RoleType
from app.staff.models.user_roles import UserRole
from app.staff.schemas.clubs import ClubCreate, ClubUpdate



@db_operation
async def get_club_by_id(session: AsyncSession, club_id: int):
    """Get club by ID with owner information"""
    if club_id <= 0:
        raise ValidationError("Club ID must be positive")

    result = await session.execute(
        select(Club).options(selectinload(Club.owner)).where(Club.id == club_id)
    )
    club = result.scalar_one_or_none()

    if not club:
        raise NotFoundError("Club", str(club_id))

    return club


@db_operation
async def get_club_by_name(session: AsyncSession, name: str):
    """Get club by name"""
    if not name or not name.strip():
        raise ValidationError("Club name cannot be empty")

    result = await session.execute(select(Club).where(Club.name == name.strip()))
    return result.scalar_one_or_none()


@db_operation
async def get_clubs_by_owner(session: AsyncSession, owner_id: int):
    """Get all clubs owned by a specific user"""
    if owner_id <= 0:
        raise ValidationError("Owner ID must be positive")

    result = await session.execute(
        select(Club)
        .options(selectinload(Club.owner))
        .where(Club.owner_id == owner_id)
        .order_by(Club.created_at.desc())
    )
    return result.scalars().all()


@db_operation
async def get_clubs_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    city: Optional[str] = None,
    name: Optional[str] = None,
):
    """Get paginated list of clubs with optional filters"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    base_query = select(Club).options(selectinload(Club.owner))
    count_query = select(func.count(Club.id))

    conditions = []

    if city:
        conditions.append(Club.city.ilike(f"%{city.strip()}%"))

    if name:
        conditions.append(Club.name.ilike(f"%{name.strip()}%"))

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
    """Create a new club with limits check and owner role assignment"""
    if owner_id <= 0:
        raise ValidationError("Owner ID must be positive")

    async def _create_club_operation(session: AsyncSession):
        # 1. Проверяем лимиты пользователя
        limits_check = await check_user_clubs_limit_before_create(session, owner_id)

        if not limits_check["can_create"]:
            raise LimitExceededError(
                "clubs", limits_check["max_clubs"], limits_check["current_clubs"]
            )

        # 2. Проверяем уникальность имени клуба
        existing_club = await session.execute(
            select(Club).where(Club.name == club.name.strip())
        )
        if existing_club.scalar_one_or_none():
            raise DuplicateError("Club", "name", club.name)

        # 3. Проверяем существование владельца
        owner_result = await session.execute(
            select(UserStaff).where(UserStaff.id == owner_id)
        )
        owner = owner_result.scalar_one_or_none()
        if not owner:
            raise NotFoundError("User", str(owner_id))

        # 4. Создаем клуб
        club_data = club.model_dump()
        club_data["owner_id"] = owner_id

        db_club = Club(**club_data)
        session.add(db_club)
        await session.flush()  # Получаем ID клуба

        # 5. Создаем owner роль для пользователя в этом клубе
        # Получаем роль owner
        owner_role_result = await session.execute(
            select(Role).where(Role.code == RoleType.owner)
        )
        owner_role = owner_role_result.scalar_one_or_none()

        if not owner_role:
            raise DatabaseError("Owner role not found in database")

        # Создаем запись в user_roles
        user_role = UserRole(
            user_id=owner_id,
            club_id=db_club.id,
            role_id=owner_role.id,
            is_active=True,
        )
        session.add(user_role)

        return db_club

    # Выполняем операцию в транзакции с retry
    db_club = await with_db_transaction(session, _create_club_operation)

    # Загружаем связанные данные
    await session.refresh(db_club, ["owner"])
    return db_club


@db_operation
async def update_club(
    session: AsyncSession,
    club_id: int,
    club_update: ClubUpdate,
    owner_id: Optional[int] = None,
) -> Club:
    """Update an existing club"""
    if club_id <= 0:
        raise ValidationError("Club ID must be positive")

    # Получаем клуб
    club_result = await session.execute(
        select(Club).options(selectinload(Club.owner)).where(Club.id == club_id)
    )
    db_club = club_result.scalar_one_or_none()

    if not db_club:
        raise NotFoundError("Club", str(club_id))

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise PermissionDeniedError(
            "update", "club", "You can only update clubs you own"
        )

    # Check if new name conflicts with existing clubs
    update_data = club_update.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] != db_club.name:
        existing_club_result = await session.execute(
            select(Club).where(Club.name == update_data["name"].strip())
        )
        existing_club = existing_club_result.scalar_one_or_none()
        if existing_club:
            raise DuplicateError("Club", "name", update_data["name"])

    # Применяем изменения
    for key, value in update_data.items():
        setattr(db_club, key, value)

    await session.commit()
    await session.refresh(db_club, ["owner", "updated_at"])

    return db_club


@db_operation
async def delete_club(
    session: AsyncSession, club_id: int, owner_id: Optional[int] = None
) -> bool:
    """Delete a club (hard delete with cascading)"""
    if club_id <= 0:
        raise ValidationError("Club ID must be positive")

    # Получаем клуб
    club_result = await session.execute(select(Club).where(Club.id == club_id))
    db_club = club_result.scalar_one_or_none()

    if not db_club:
        raise NotFoundError("Club", str(club_id))

    # If owner_id is provided, verify ownership
    if owner_id and db_club.owner_id != owner_id:
        raise PermissionDeniedError(
            "delete", "club", "You can only delete clubs you own"
        )

    # Manually delete related entities to avoid DB integrity errors if ON DELETE CASCADE is missing
    await _manual_cascade_delete_club(session, club_id)

    # Удаляем клуб (связанные записи удалятся автоматически из-за cascade)
    await session.delete(db_club)
    await session.commit()

    return True


async def _manual_cascade_delete_club(session: AsyncSession, club_id: int):
    """
    Manually delete related entities for a club to ensure integrity.
    Debug version to trace what is being found.
    """
    # 1. Fetch Section IDs
    result = await session.execute(text("SELECT id FROM sections WHERE club_id = :cid"), {"cid": club_id})
    section_ids = [r[0] for r in result.fetchall()]
    print(f"DEBUG: Found sections for club {club_id}: {section_ids}")
    
    if not section_ids:
        return

    # 2. Fetch Group IDs
    if section_ids:
        s_ids_str = ",".join(map(str, section_ids))
        result = await session.execute(text(f"SELECT id FROM groups WHERE section_id IN ({s_ids_str})"))
        group_ids = [r[0] for r in result.fetchall()]
        print(f"DEBUG: Found groups: {group_ids}")
    else:
        group_ids = []

    # 3. Fetch Lesson IDs
    if group_ids:
        g_ids_str = ",".join(map(str, group_ids))
        result = await session.execute(text(f"SELECT id FROM lessons WHERE group_id IN ({g_ids_str})"))
        lesson_ids = [r[0] for r in result.fetchall()]
        print(f"DEBUG: Found lessons: {lesson_ids}")
        
        # 4. Fetch LessonBooking IDs
        if lesson_ids:
            l_ids_str = ",".join(map(str, lesson_ids))
            result = await session.execute(text(f"SELECT id FROM lesson_bookings WHERE lesson_id IN ({l_ids_str})"))
            booking_ids = [r[0] for r in result.fetchall()]
            print(f"DEBUG: Found bookings: {booking_ids}")
            
            # DELETE Bookings
            if booking_ids:
                await session.execute(text(f"DELETE FROM lesson_bookings WHERE id IN ({','.join(map(str, booking_ids))})"))
                print("DEBUG: Deleted bookings")
            
            # DELETE Lessons
            await session.execute(text(f"DELETE FROM lessons WHERE id IN ({l_ids_str})"))
            print("DEBUG: Deleted lessons")

        # DELETE Enrollments
        # Select enrollments to debug?
        result = await session.execute(text(f"SELECT id FROM student_enrollments WHERE group_id IN ({g_ids_str})"))
        enrollment_ids = [r[0] for r in result.fetchall()]
        print(f"DEBUG: Found enrollments: {enrollment_ids}")
        if enrollment_ids:
             await session.execute(text(f"DELETE FROM student_enrollments WHERE id IN ({','.join(map(str, enrollment_ids))})"))
        
        # DELETE Groups
        await session.execute(text(f"DELETE FROM groups WHERE id IN ({g_ids_str})"))
        print("DEBUG: Deleted groups")

    # DELETE Sections
    if section_ids:
        await session.execute(text(f"DELETE FROM sections WHERE id IN ({s_ids_str})"))
        print("DEBUG: Deleted sections")



@db_operation
async def check_user_club_permission(
    session: AsyncSession, user_id: int, club_id: int
) -> bool:
    """Check if user has permission to manage a club (is owner or has admin role)"""
    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    if club_id <= 0:
        raise ValidationError("Club ID must be positive")

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


@db_operation
async def get_user_clubs_with_roles(session: AsyncSession, user_id: int):
    """Get all clubs where user has any role"""
    if user_id <= 0:
        raise ValidationError("User ID must be positive")

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


@db_operation
async def check_user_clubs_limit_before_create(
    session: AsyncSession, user_id: int
) -> dict:
    """
    Проверить лимиты пользователя перед созданием клуба
    Возвращает информацию о возможности создания
    """
    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Получаем пользователя
    user_result = await session.execute(
        select(UserStaff).where(UserStaff.id == user_id)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User", str(user_id))

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
