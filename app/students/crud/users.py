from typing import Any, Dict
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.students.models.users import UserStudent
from app.core.config import TELEGRAM_BOT_TOKEN
from app.core.telegram_auth import TelegramAuth
from app.students.schemas.users import (
    UserStudentCreate,
    UserStudentUpdate,
    PreferencesUpdate,
    UserStudentFilters,
)

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN)


async def get_user_student_by_telegram_id(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_student_by_id(session: AsyncSession, user_id: int):
    result = await session.execute(select(UserStudent).where(UserStudent.id == user_id))
    return result.scalar_one_or_none()


async def get_user_students_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    filters: UserStudentFilters = None,
):
    # Базовый запрос
    base_query = select(UserStudent)
    count_query = select(func.count(UserStudent.id))

    # Применяем фильтры если они есть
    if filters:
        conditions = []

        if filters.first_name:
            conditions.append(UserStudent.first_name.ilike(f"%{filters.first_name}%"))

        if filters.last_name:
            conditions.append(UserStudent.last_name.ilike(f"%{filters.last_name}%"))

        if filters.phone_number:
            conditions.append(
                UserStudent.phone_number.ilike(f"%{filters.phone_number}%")
            )

        if filters.username:
            conditions.append(UserStudent.username.ilike(f"%{filters.username}%"))

        # Применяем условия к запросам
        if conditions:
            filter_condition = and_(*conditions)
            base_query = base_query.where(filter_condition)
            count_query = count_query.where(filter_condition)

    # Получаем общее количество записей
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Получаем пагинированные результаты
    query = base_query.offset(skip).limit(limit).order_by(UserStudent.created_at.desc())
    result = await session.execute(query)
    users = result.scalars().all()

    return users, total


async def create_user_student(
    session: AsyncSession, user: UserStudentCreate, current_user: Dict[str, Any]
):
    contact_data = telegram_auth.authenticate_contact_request(user.contact_init_data)
    phone_number = contact_data["contact"]["phone_number"]

    default_preferences = {
        "language": current_user.get("language_code", None),
        "dark_mode": False,
        "notifications": True,
        "timezone": "UTC+5",
    }

    user_preferences = user.preferences or {}
    merged_preferences = {**default_preferences, **user_preferences}

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
        db_user = UserStudent(**user_data)
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        return db_user
    except:
        await session.rollback()
        raise


async def update_user_student(
    session: AsyncSession, telegram_id: int, user: UserStudentUpdate
):
    db_user = await get_user_student_by_telegram_id(session, telegram_id)
    if not db_user:
        return None

    user_data = user.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(db_user, key, value)

    await session.commit()
    await session.refresh(db_user)
    return db_user


async def update_user_student_preferences(
    session: AsyncSession, preferences: PreferencesUpdate, telegram_id: int
):
    db_user = await get_user_student_by_telegram_id(session, telegram_id)
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


async def get_user_student_preference(
    session: AsyncSession, telegram_id: int, preference_key: str
):
    db_user = await get_user_student_by_telegram_id(session, telegram_id)
    if not db_user or not db_user.preferences:
        return None

    return db_user.preferences.get(preference_key)


async def delete_user_student(session: AsyncSession, telegram_id: int) -> bool:
    """
    Удалить студента по telegram_id.
    """
    db_user = await get_user_student_by_telegram_id(session, telegram_id)
    if not db_user:
        return False

    try:
        await session.delete(db_user)
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        raise
