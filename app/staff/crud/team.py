from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict
from sqlalchemy import and_, func, or_
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation
from app.core.exceptions import ValidationError
from app.staff.models.users import UserStaff
from app.staff.models.clubs import Club
from app.staff.models.sections import Section
from app.staff.models.roles import Role, RoleType
from app.staff.models.user_roles import UserRole
from app.staff.schemas.team import TeamMember, ClubRole, TeamFilters


@db_operation
async def get_user_clubs(session: AsyncSession, user_id: int) -> List[int]:
    """Получить ID всех клубов где работает пользователь"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    result = await session.execute(
        select(UserRole.club_id)
        .where(and_(UserRole.user_id == user_id, UserRole.is_active == True))
        .distinct()
    )
    return [club_id for club_id, in result.fetchall()]


@db_operation
async def get_team_members_raw_data(
    session: AsyncSession, user_clubs: List[int], filters: Optional[TeamFilters] = None
) -> List[Dict[str, Any]]:
    """Получить сырые данные о всех staff из общих клубов"""

    if not user_clubs:
        return []

    # Базовый запрос
    query = (
        select(
            UserStaff.id,
            UserStaff.telegram_id,
            UserStaff.first_name,
            UserStaff.last_name,
            UserStaff.username,
            UserStaff.phone_number,
            UserStaff.photo_url,
            UserStaff.created_at,
            UserStaff.updated_at,
            Club.id.label("club_id"),
            Club.name.label("club_name"),
            Role.code.label("role"),
            UserRole.joined_at,
            UserRole.is_active,
            func.coalesce(
                func.count(Section.id).filter(Section.coach_id == UserStaff.id), 0
            ).label("sections_count"),
        )
        .select_from(UserStaff)
        .join(UserRole, UserStaff.id == UserRole.user_id)
        .join(Club, UserRole.club_id == Club.id)
        .join(Role, UserRole.role_id == Role.id)
        .outerjoin(
            Section,
            and_(
                Section.club_id == Club.id,
                Section.coach_id == UserStaff.id,
                Section.active == True,
            ),
        )
        .where(Club.id.in_(user_clubs))
    )

    # Применяем фильтры
    conditions = []

    if filters:
        if filters.club_id:
            if filters.club_id not in user_clubs:
                raise ValidationError("Access denied to this club")
            conditions.append(Club.id == filters.club_id)

        if filters.role:
            conditions.append(Role.code == filters.role)

        if filters.name:
            name_filter = f"%{filters.name.strip()}%"
            conditions.append(
                or_(
                    UserStaff.first_name.ilike(name_filter),
                    UserStaff.last_name.ilike(name_filter),
                    func.concat(UserStaff.first_name, " ", UserStaff.last_name).ilike(
                        name_filter
                    ),
                )
            )

        if filters.section_id:
            # Для фильтра по секции - показываем только тренеров этой секции
            conditions.append(Section.id == filters.section_id)
            conditions.append(Role.code == RoleType.coach)

        if filters.active_only:
            conditions.append(UserRole.is_active == True)
    else:
        # По умолчанию показываем только активные роли
        conditions.append(UserRole.is_active == True)

    if conditions:
        query = query.where(and_(*conditions))

    # Группировка для подсчета секций
    query = query.group_by(
        UserStaff.id,
        UserStaff.telegram_id,
        UserStaff.first_name,
        UserStaff.last_name,
        UserStaff.username,
        UserStaff.phone_number,
        UserStaff.photo_url,
        UserStaff.created_at,
        UserStaff.updated_at,
        Club.id,
        Club.name,
        Role.code,
        UserRole.joined_at,
        UserRole.is_active,
    )

    # Сортировка
    query = query.order_by(UserStaff.first_name, UserStaff.last_name, Club.name)

    result = await session.execute(query)
    return [dict(row._mapping) for row in result.fetchall()]


def group_team_members_data(raw_data: List[Dict[str, Any]]) -> List[TeamMember]:
    """Группировать сырые данные по пользователям"""

    users_data = defaultdict(lambda: {"user_info": None, "clubs_and_roles": []})

    for row in raw_data:
        user_id = row["id"]

        # Сохраняем информацию о пользователе (только один раз)
        if users_data[user_id]["user_info"] is None:
            users_data[user_id]["user_info"] = {
                "id": row["id"],
                "telegram_id": row["telegram_id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "username": row["username"],
                "phone_number": row["phone_number"],
                "photo_url": row["photo_url"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }

        # Добавляем информацию о роли в клубе
        club_role = ClubRole(
            club_id=row["club_id"],
            club_name=row["club_name"],
            role=row["role"],
            joined_at=row["joined_at"],
            is_active=row["is_active"],
            sections_count=row["sections_count"],
        )

        users_data[user_id]["clubs_and_roles"].append(club_role)

    # Создаем объекты TeamMember
    team_members = []
    for user_data in users_data.values():
        member = TeamMember(
            **user_data["user_info"], clubs_and_roles=user_data["clubs_and_roles"]
        )
        team_members.append(member)

    # Сортируем по имени
    team_members.sort(key=lambda x: (x.first_name, x.last_name or ""))

    return team_members


@db_operation
async def get_team_members_paginated(
    session: AsyncSession,
    user_id: int,
    skip: int = 0,
    limit: int = 20,
    filters: Optional[TeamFilters] = None,
) -> Tuple[List[TeamMember], int]:
    """Получить пагинированный список участников команды"""

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    # Получаем клубы пользователя
    user_clubs = await get_user_clubs(session, user_id)

    if not user_clubs:
        return [], 0

    # Получаем сырые данные
    raw_data = await get_team_members_raw_data(session, user_clubs, filters)

    # Группируем данные
    team_members = group_team_members_data(raw_data)

    # Применяем пагинацию
    total = len(team_members)
    paginated_members = team_members[skip : skip + limit]

    return paginated_members, total


@db_operation
async def get_user_clubs_info(
    session: AsyncSession, user_id: int
) -> List[Dict[str, Any]]:
    """Получить информацию о клубах пользователя для контекста"""

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    result = await session.execute(
        select(Club.id, Club.name, Role.code.label("role"))
        .select_from(UserRole)
        .join(Club, UserRole.club_id == Club.id)
        .join(Role, UserRole.role_id == Role.id)
        .where(and_(UserRole.user_id == user_id, UserRole.is_active == True))
        .order_by(Club.name)
    )

    return [
        {"club_id": row.id, "club_name": row.name, "user_role": row.role.value}
        for row in result.fetchall()
    ]


@db_operation
async def get_team_stats(session: AsyncSession, user_id: int) -> Dict[str, Any]:
    """Получить статистику по команде"""

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    user_clubs = await get_user_clubs(session, user_id)

    if not user_clubs:
        return {"total_members": 0, "by_role": {}, "by_club": {}, "active_members": 0}

    # Статистика по ролям
    role_stats_result = await session.execute(
        select(Role.code, func.count(UserRole.user_id.distinct()).label("count"))
        .select_from(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(and_(UserRole.club_id.in_(user_clubs), UserRole.is_active == True))
        .group_by(Role.code)
    )

    by_role = {role.value: count for role, count in role_stats_result.fetchall()}

    # Статистика по клубам
    club_stats_result = await session.execute(
        select(Club.name, func.count(UserRole.user_id.distinct()).label("count"))
        .select_from(UserRole)
        .join(Club, UserRole.club_id == Club.id)
        .where(and_(UserRole.club_id.in_(user_clubs), UserRole.is_active == True))
        .group_by(Club.name)
    )

    by_club = {club_name: count for club_name, count in club_stats_result.fetchall()}

    # Общее количество уникальных участников
    total_result = await session.execute(
        select(func.count(UserRole.user_id.distinct())).where(
            and_(UserRole.club_id.in_(user_clubs), UserRole.is_active == True)
        )
    )

    total_members = total_result.scalar() or 0

    return {
        "total_members": total_members,
        "by_role": by_role,
        "by_club": by_club,
        "active_members": total_members,  # Поскольку мы считаем только активных
    }
