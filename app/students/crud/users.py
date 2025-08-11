from typing import Any, Dict
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    AuthenticationError,
    TelegramAuthError,
)
from app.core.validations import clean_phone_number
from app.students.models.users import UserStudent
from app.core.config import TELEGRAM_BOT_TOKEN_STUDENT
from app.core.telegram_auth import TelegramAuth
from app.students.schemas.users import (
    UserStudentCreate,
    UserStudentUpdate,
    PreferencesUpdate,
    UserStudentFilters,
)

if not TELEGRAM_BOT_TOKEN_STUDENT:
    raise ValidationError("TELEGRAM_BOT_TOKEN_STUDENT is required")

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN_STUDENT)


@db_operation
async def get_user_student_by_telegram_id(session: AsyncSession, telegram_id: int):
    """Получить student пользователя по Telegram ID"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    result = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@db_operation
async def get_user_student_by_id(session: AsyncSession, user_id: int):
    """Получить student пользователя по ID"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    result = await session.execute(select(UserStudent).where(UserStudent.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundError("Student user", str(user_id))

    return user


@db_operation
async def get_user_students_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    filters: UserStudentFilters = None,
):
    """Получить пагинированный список student пользователей"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    # Базовый запрос
    base_query = select(UserStudent)
    count_query = select(func.count(UserStudent.id))

    # Применяем фильтры если они есть
    if filters:
        conditions = []

        if filters.first_name:
            conditions.append(
                UserStudent.first_name.ilike(f"%{filters.first_name.strip()}%")
            )

        if filters.last_name:
            conditions.append(
                UserStudent.last_name.ilike(f"%{filters.last_name.strip()}%")
            )

        if filters.phone_number:
            conditions.append(
                UserStudent.phone_number.ilike(f"%{filters.phone_number.strip()}%")
            )

        if filters.username:
            conditions.append(
                UserStudent.username.ilike(f"%{filters.username.strip()}%")
            )

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


@db_operation
async def create_user_student(
    session: AsyncSession, user: UserStudentCreate, current_user: Dict[str, Any]
):
    """Создать нового student пользователя"""
    if not current_user or not current_user.get("id"):
        raise AuthenticationError("Valid user authentication data required")

    telegram_id = current_user.get("id")

    # Проверяем существование пользователя
    existing_user = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    if existing_user.scalar_one_or_none():
        raise DuplicateError("Student user", "telegram_id", str(telegram_id))

    # Аутентификация контактных данных
    try:
        contact_data = telegram_auth.authenticate_contact_request(
            user.contact_init_data
        )
        raw_phone = contact_data["contact"]["phone_number"]
        phone_number = clean_phone_number(raw_phone)
    except Exception as e:
        raise TelegramAuthError(f"Contact authentication failed: {str(e)}")

    # Формируем preferences
    default_preferences = {
        "language": current_user.get("language_code", "ru"),
        "dark_mode": False,
        "notifications": True,
    }
    user_preferences = user.preferences or {}
    merged_preferences = {**default_preferences, **user_preferences}

    # Создаем пользователя
    user_data = {
        "telegram_id": telegram_id,
        "first_name": current_user.get("first_name"),
        "last_name": current_user.get("last_name"),
        "username": current_user.get("username"),
        "phone_number": phone_number,
        "photo_url": current_user.get("photo_url"),
        "preferences": merged_preferences,
    }

    db_user = UserStudent(**user_data)
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


@db_operation
async def update_user_student(
    session: AsyncSession, telegram_id: int, user: UserStudentUpdate
):
    """Обновить данные student пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    db_user = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Student user", str(telegram_id))

    user_data = user.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(user_obj, key, value)

    await session.commit()
    await session.refresh(user_obj)
    return user_obj


@db_operation
async def update_user_student_preferences(
    session: AsyncSession, preferences: PreferencesUpdate, telegram_id: int
):
    """Обновить preferences пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    db_user = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Student user", str(telegram_id))

    current_preferences = user_obj.preferences or {}
    new_preferences_dict = preferences.model_dump(exclude_unset=True)

    # Merge preferences
    updated_preferences = {**current_preferences, **new_preferences_dict}
    user_obj.preferences = updated_preferences

    await session.commit()
    await session.refresh(user_obj)
    return user_obj


@db_operation
async def get_user_student_preference(
    session: AsyncSession, telegram_id: int, preference_key: str
):
    """Получить конкретную preference пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    if not preference_key or not preference_key.strip():
        raise ValidationError("Preference key cannot be empty")

    db_user = await session.execute(
        select(UserStudent).where(UserStudent.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Student user", str(telegram_id))

    if not user_obj.preferences:
        return None

    return user_obj.preferences.get(preference_key.strip())
