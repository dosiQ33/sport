from typing import Any, Dict
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.stuff.models.users import UserStuff
from app.core.config import TELEGRAM_BOT_TOKEN
from app.core.telegram_auth import TelegramAuth
from app.stuff.schemas.users import (
    UserStuffCreate,
    UserStuffUpdate,
    UserStuffPreferencesUpdate,
    UserStuffFilters,
)

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN)


async def get_user_stuff_by_telegram_id(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(UserStuff).where(UserStuff.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_user_stuff_by_id(session: AsyncSession, user_id: int):
    result = await session.execute(select(UserStuff).where(UserStuff.id == user_id))
    return result.scalar_one_or_none()


async def get_users_stuff_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    filters: UserStuffFilters = None,
):
    # Базовый запрос
    base_query = select(UserStuff)
    count_query = select(func.count(UserStuff.id))

    # Применяем фильтры если они есть
    if filters:
        conditions = []

        if filters.first_name:
            conditions.append(UserStuff.first_name.ilike(f"%{filters.first_name}%"))

        if filters.last_name:
            conditions.append(UserStuff.last_name.ilike(f"%{filters.last_name}%"))

        if filters.phone_number:
            conditions.append(UserStuff.phone_number.ilike(f"%{filters.phone_number}%"))

        if filters.username:
            conditions.append(UserStuff.username.ilike(f"%{filters.username}%"))

        # Применяем условия к запросам
        if conditions:
            filter_condition = and_(*conditions)
            base_query = base_query.where(filter_condition)
            count_query = count_query.where(filter_condition)

    # Получаем общее количество записей
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Получаем пагинированные результаты
    query = base_query.offset(skip).limit(limit).order_by(UserStuff.created_at.desc())
    result = await session.execute(query)
    users = result.scalars().all()

    return users, total


async def create_user_stuff(
    session: AsyncSession, user: UserStuffCreate, current_user: Dict[str, Any]
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
        db_user = UserStuff(**user_data)
        session.add(db_user)
        await session.commit()
        await session.refresh(db_user)
        return db_user
    except:
        await session.rollback()
        raise


async def update_user_stuff(
    session: AsyncSession, telegram_id: int, user: UserStuffUpdate
):
    db_user = await get_user_stuff_by_telegram_id(session, telegram_id)
    if not db_user:
        return None

    user_data = user.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(db_user, key, value)

    await session.commit()
    await session.refresh(db_user)
    return db_user


async def update_user_stuff_preferences(
    session: AsyncSession, preferences: UserStuffPreferencesUpdate, telegram_id: int
):
    db_user = await get_user_stuff_by_telegram_id(session, telegram_id)
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


async def get_user_stuff_preference(
    session: AsyncSession, telegram_id: int, preference_key: str
):
    db_user = await get_user_stuff_by_telegram_id(session, telegram_id)
    if not db_user or not db_user.preferences:
        return None

    return db_user.preferences.get(preference_key)
