from typing import Any, Dict
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    AuthenticationError,
    TelegramAuthError,
)
from app.staff.crud.invitations import (
    get_any_active_invitation_by_phone,
    mark_invitation_as_used,
)
from app.staff.models.roles import Role, RoleType
from app.staff.models.user_roles import UserRole
from app.staff.models.users import UserStaff
from app.staff.models.clubs import Club
from app.staff.models.sections import Section
from app.core.config import TELEGRAM_BOT_TOKEN
from app.core.telegram_auth import TelegramAuth
from app.staff.schemas.users import (
    UserStaffCreate,
    UserStaffUpdate,
    UserStaffPreferencesUpdate,
    UserStaffFilters,
    UserLimitsUpdate,
)

if not TELEGRAM_BOT_TOKEN:
    raise ValidationError("TELEGRAM_BOT_TOKEN is required")

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN)


@db_operation
async def get_user_staff_by_telegram_id(session: AsyncSession, telegram_id: int):
    """Получить staff пользователя по Telegram ID"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    result = await session.execute(
        select(UserStaff).where(UserStaff.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


@db_operation
async def get_user_staff_by_id(session: AsyncSession, user_id: int):
    """Получить staff пользователя по ID"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    result = await session.execute(select(UserStaff).where(UserStaff.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise NotFoundError("Staff user", str(user_id))

    return user


@db_operation
async def get_user_staff_by_phone(session: AsyncSession, phone_number: str):
    """Получить пользователя по номеру телефона"""
    if not phone_number or not phone_number.strip():
        raise ValidationError("Phone number cannot be empty")

    result = await session.execute(
        select(UserStaff).where(UserStaff.phone_number == phone_number.strip())
    )
    return result.scalar_one_or_none()


@db_operation
async def get_users_staff_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    filters: UserStaffFilters = None,
):
    """Получить пагинированный список staff пользователей"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    # Базовый запрос
    base_query = select(UserStaff)
    count_query = select(func.count(UserStaff.id))

    # Применяем фильтры если они есть
    if filters:
        conditions = []

        if filters.first_name:
            conditions.append(
                UserStaff.first_name.ilike(f"%{filters.first_name.strip()}%")
            )

        if filters.last_name:
            conditions.append(
                UserStaff.last_name.ilike(f"%{filters.last_name.strip()}%")
            )

        if filters.phone_number:
            conditions.append(
                UserStaff.phone_number.ilike(f"%{filters.phone_number.strip()}%")
            )

        if filters.username:
            conditions.append(UserStaff.username.ilike(f"%{filters.username.strip()}%"))

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
    """Создать нового staff пользователя"""
    if not current_user or not current_user.get("id"):
        raise AuthenticationError("Valid user authentication data required")

    telegram_id = current_user.get("id")

    async def _create_user_operation(session: AsyncSession):
        # Проверяем существование пользователя
        existing_user = await session.execute(
            select(UserStaff).where(UserStaff.telegram_id == telegram_id)
        )
        if existing_user.scalar_one_or_none():
            raise DuplicateError("Staff user", "telegram_id", str(telegram_id))

        # Аутентификация контактных данных
        try:
            contact_data = telegram_auth.authenticate_contact_request(
                user.contact_init_data
            )
            phone_number = contact_data["contact"]["phone_number"]
        except Exception as e:
            raise TelegramAuthError(f"Contact authentication failed: {str(e)}")

        # Проверяем активные приглашения
        active_invitations = await get_any_active_invitation_by_phone(
            session, phone_number
        )
        if not active_invitations:
            raise NotFoundError(
                "Active invitation",
                f"No valid invitation found for phone {phone_number}. Please contact administrator.",
            )

        # Выбираем приглашение с наивысшим приоритетом
        priority_order = {RoleType.owner: 3, RoleType.admin: 2, RoleType.coach: 1}
        invitation = max(
            active_invitations, key=lambda inv: priority_order.get(inv.role, 0)
        )

        # Формируем preferences
        default_preferences = {
            "language": current_user.get("language_code", "ru"),
            "dark_mode": False,
            "notifications": True,
        }
        user_preferences = user.preferences or {}
        merged_preferences = {**default_preferences, **user_preferences}

        # Устанавливаем лимиты в зависимости от роли
        if invitation.role == RoleType.owner:
            default_limits = {"clubs": 1, "sections": 1}
        else:
            default_limits = {"clubs": 0, "sections": 0}

        # Создаем пользователя
        user_data = {
            "telegram_id": telegram_id,
            "first_name": current_user.get("first_name"),
            "last_name": current_user.get("last_name"),
            "username": current_user.get("username"),
            "phone_number": phone_number,
            "photo_url": current_user.get("photo_url"),
            "preferences": merged_preferences,
            "limits": default_limits,
        }

        db_user = UserStaff(**user_data)
        session.add(db_user)
        await session.flush()  # Получаем ID пользователя

        # Обрабатываем все активные приглашения
        for inv in active_invitations:
            if inv.club_id:
                # Получаем роль
                role_result = await session.execute(
                    select(Role).where(Role.code == inv.role)
                )
                role = role_result.scalar_one_or_none()
                if not role:
                    raise NotFoundError("Role", inv.role.value)

                # Создаем запись о роли в клубе
                user_role = UserRole(
                    user_id=db_user.id,
                    club_id=inv.club_id,
                    role_id=role.id,
                    is_active=True,
                )
                session.add(user_role)

            # Помечаем приглашение как использованное
            await mark_invitation_as_used(session, inv.id, db_user.id)

        return db_user

    # Выполняем операцию в транзакции
    db_user = await with_db_transaction(session, _create_user_operation)
    return db_user


@db_operation
async def update_user_staff(
    session: AsyncSession, telegram_id: int, user: UserStaffUpdate
):
    """Обновить данные staff пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    db_user = await session.execute(
        select(UserStaff).where(UserStaff.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Staff user", str(telegram_id))

    user_data = user.model_dump(exclude_unset=True)
    for key, value in user_data.items():
        setattr(user_obj, key, value)

    await session.commit()
    await session.refresh(user_obj)
    return user_obj


@db_operation
async def update_user_staff_preferences(
    session: AsyncSession, preferences: UserStaffPreferencesUpdate, telegram_id: int
):
    """Обновить preferences пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    db_user = await session.execute(
        select(UserStaff).where(UserStaff.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Staff user", str(telegram_id))

    current_preferences = user_obj.preferences or {}
    new_preferences_dict = preferences.model_dump(exclude_unset=True)

    # Merge preferences
    updated_preferences = {**current_preferences, **new_preferences_dict}
    user_obj.preferences = updated_preferences

    await session.commit()
    await session.refresh(user_obj)
    return user_obj


@db_operation
async def get_user_staff_preference(
    session: AsyncSession, telegram_id: int, preference_key: str
):
    """Получить конкретную preference пользователя"""
    if not telegram_id or telegram_id <= 0:
        raise ValidationError("Telegram ID must be positive")

    if not preference_key or not preference_key.strip():
        raise ValidationError("Preference key cannot be empty")

    db_user = await session.execute(
        select(UserStaff).where(UserStaff.telegram_id == telegram_id)
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Staff user", str(telegram_id))

    if not user_obj.preferences:
        return None

    return user_obj.preferences.get(preference_key.strip())


@db_operation
async def update_user_limits_by_phone(
    session: AsyncSession, phone_number: str, limits_update: UserLimitsUpdate
) -> UserStaff:
    """Обновить лимиты пользователя по номеру телефона (только для суперадмина)"""
    if not phone_number or not phone_number.strip():
        raise ValidationError("Phone number cannot be empty")

    db_user = await session.execute(
        select(UserStaff).where(UserStaff.phone_number == phone_number.strip())
    )
    user_obj = db_user.scalar_one_or_none()

    if not user_obj:
        raise NotFoundError("Staff user", f"No user found with phone {phone_number}")

    # Получаем текущие лимиты
    current_limits = user_obj.limits or {"clubs": 0, "sections": 0}

    # Обновляем только переданные значения
    update_data = limits_update.model_dump(exclude_unset=True)
    updated_limits = {**current_limits, **update_data}

    user_obj.limits = updated_limits

    await session.commit()
    await session.refresh(user_obj)
    return user_obj


@db_operation
async def get_user_current_counts(
    session: AsyncSession, user_id: int
) -> Dict[str, int]:
    """Получить текущее количество клубов и секций пользователя"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Считаем клубы
    clubs_result = await session.execute(
        select(func.count(Club.id)).where(Club.owner_id == user_id)
    )
    clubs_count = clubs_result.scalar() or 0

    # Считаем секции (те, где пользователь является owner клуба)
    sections_result = await session.execute(
        select(func.count(Section.id))
        .join(Club, Section.club_id == Club.id)
        .where(Club.owner_id == user_id)
    )
    sections_count = sections_result.scalar() or 0

    return {"clubs": clubs_count, "sections": sections_count}
