# app/staff/crud/users.py
from typing import Any, Dict
from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role
from app.core.config import TELEGRAM_BOT_TOKEN
from app.core.telegram_auth import TelegramAuth
from app.staff.schemas.users import (
    UserStaffCreate,
    UserStaffUpdate,
    UserStaffPreferencesUpdate,
    UserStaffFilters,
)
from app.staff.crud.invitations import get_invitation_by_phone, mark_invitation_as_used

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN)


async def get_user_staff_by_telegram_id(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(UserStaff).where(UserStaff.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_staff_by_id(session: AsyncSession, user_id: int):
    result = await session.execute(select(UserStaff).where(UserStaff.id == user_id))
    return result.scalar_one_or_none()


async def get_users_staff_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    filters: UserStaffFilters = None,
):
    # Базовый запрос
    base_query = select(UserStaff)
    count_query = select(func.count(UserStaff.id))

    # Применяем фильтры если они есть
    if filters:
        conditions = []

        if filters.first_name:
            conditions.append(UserStaff.first_name.ilike(f"%{filters.first_name}%"))

        if filters.last_name:
            conditions.append(UserStaff.last_name.ilike(f"%{filters.last_name}%"))

        if filters.phone_number:
            conditions.append(UserStaff.phone_number.ilike(f"%{filters.phone_number}%"))

        if filters.username:
            conditions.append(UserStaff.username.ilike(f"%{filters.username}%"))

        # Применяем условия к запросам
        if conditions:
            filter_condition = and_(*conditions)
            base_query = base_query.where(filter_condition)
            count_query = count_query.where(filter_condition)

    # Получаем общее количество записей
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Получаем пагинированные результаты
    query = base_query.offset(skip).limit(limit).order_by(UserStaff.created_at.desc())
    result = await session.execute(query)
    users = result.scalars().all()

    return users, total


async def create_user_staff(
    session: AsyncSession, user: UserStaffCreate, current_user: Dict[str, Any]
):
    """Создать пользователя staff с проверкой приглашения"""

    # Проверяем контактные данные
    contact_data = telegram_auth.authenticate_contact_request(user.contact_init_data)
    phone_number = contact_data["contact"]["phone_number"]

    # Проверяем, что пользователь с таким telegram_id не существует
    existing_user = await get_user_staff_by_telegram_id(session, current_user.get("id"))
    if existing_user:
        raise ValueError("User with this Telegram ID already exists")

    # Проверяем наличие приглашения
    invitation = await get_invitation_by_phone(session, phone_number)
    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid invitation found for this phone number. Please contact the administrator.",
        )

    default_preferences = {
        "language": current_user.get("language_code", None),
        "dark_mode": False,
        "notifications": True,
        "timezone": "UTC+5",
    }

    user_preferences = user.preferences or {}
    merged_preferences = {**default_preferences, **user_preferences}

    # Создаем пользователя с лимитами из приглашения
    user_data = {
        "telegram_id": current_user.get("id"),
        "first_name": current_user.get("first_name"),
        "last_name": current_user.get("last_name", None),
        "username": current_user.get("username", None),
        "phone_number": phone_number,
        "photo_url": current_user.get("photo_url", None),
        "preferences": merged_preferences,
    }

    try:
        # Создаем пользователя
        db_user = UserStaff(**user_data)
        session.add(db_user)
        await session.flush()  # Получаем ID пользователя

        # Если приглашение для конкретного клуба, создаем роль
        if invitation.club_id:
            # Получаем ID роли
            role_result = await session.execute(
                select(Role).where(Role.code == invitation.role)
            )
            role = role_result.scalar_one()

            # Создаем запись о роли в клубе
            user_role = UserRole(
                user_id=db_user.id,
                club_id=invitation.club_id,
                role_id=role.id,
                is_active=True,
            )
            session.add(user_role)

        # Помечаем приглашение как использованное
        await mark_invitation_as_used(session, invitation.id, db_user.id)

        await session.commit()
        await session.refresh(db_user)
        return db_user
    except Exception as e:
        await session.rollback()
        raise


async def update_user_staff(
    session: AsyncSession, telegram_id: int, user: UserStaffUpdate
):
    db_user = await get_user_staff_by_telegram_id(session, telegram_id)
    if not db_user:
        return None

    user_data = user.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(db_user, key, value)

    await session.commit()
    await session.refresh(db_user)
    return db_user


async def update_user_staff_preferences(
    session: AsyncSession, preferences: UserStaffPreferencesUpdate, telegram_id: int
):
    db_user = await get_user_staff_by_telegram_id(session, telegram_id)
    if not db_user:
        return None

    current_preferences = db_user.preferences or {}
    new_preferences_dict = preferences.model_dump(exclude_unset=True)

    # Merge preferences
    updated_preferences = {**current_preferences, **new_preferences_dict}
    db_user.preferences = updated_preferences

    await session.commit()
    await session.refresh(db_user)
    return db_user


async def get_user_staff_preference(
    session: AsyncSession, telegram_id: int, preference_key: str
):
    db_user = await get_user_staff_by_telegram_id(session, telegram_id)
    if not db_user or not db_user.preferences:
        return None

    return db_user.preferences.get(preference_key)


async def delete_user_staff(session: AsyncSession, telegram_id: int) -> bool:
    """
    Удалить пользователя staff по telegram_id.
    Благодаря cascade в моделях, все связанные записи удалятся автоматически.
    """
    db_user = await get_user_staff_by_telegram_id(session, telegram_id)
    if not db_user:
        return False

    try:
        await session.delete(db_user)
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        raise


async def check_user_is_superadmin(session: AsyncSession, user_id: int) -> bool:
    """Проверить, является ли пользователь суперадмином"""
    user = await get_user_staff_by_id(session, user_id)
    return user and user.is_superadmin
