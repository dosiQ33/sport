from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from sqlalchemy import func, select, or_
from app.core.database import get_session
from app.core.dependencies import verify_superadmin_token
from app.core.exceptions import ValidationError, NotFoundError
from app.staff.schemas.invitations import (
    InvitationCreateBySuperAdmin,
    InvitationRead,
    InvitationListResponse,
)
from app.staff.crud.users import (
    get_user_staff_by_phone,
    get_user_current_counts,
    update_user_limits_by_phone,
)
from app.staff.models.users import UserStaff
from app.staff.models.clubs import Club
from app.staff.models.sections import Section
from app.staff.models.invitations import InvitationStatus
from app.students.models.users import UserStudent
from app.staff.schemas.users import UserLimitsUpdate, UserStaffRead
from app.staff.crud.invitations import (
    create_invitation_by_superadmin,
    get_invitations_paginated,
    get_invitation_stats,
    cleanup_expired_invitations,
)

router = APIRouter(prefix="/superadmin", tags=["SuperAdmin"])


@router.post("/invitations", response_model=InvitationRead)
async def create_owner_invitation(
    invitation: InvitationCreateBySuperAdmin,
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Создать приглашение для владельца клуба (только SuperAdmin).

    - **phone_number**: Номер телефона приглашаемого
    - **role**: Должна быть 'owner'
    - **club_id**: Должен быть null для owner приглашений

    Требуется заголовок: X-SuperAdmin-Token
    """
    # Дополнительная проверка роли
    if invitation.role.value != "owner":
        raise ValidationError("SuperAdmin can only create invitations for owners")

    # Все остальные проверки и ошибки обрабатываются в CRUD
    db_invitation = await create_invitation_by_superadmin(
        db, invitation, created_by_type="superadmin"
    )
    return db_invitation


@router.get("/invitations", response_model=InvitationListResponse)
async def get_all_invitations(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    status: Optional[InvitationStatus] = Query(None, description="Filter by status"),
    include_expired: bool = Query(False, description="Include expired invitations"),
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Получить все приглашения (только SuperAdmin).

    - **page**: Page number (starts from 1)
    - **size**: Number of invitations per page (max 100)
    - **status**: Filter by status (pending/accepted/declined/auto_accepted/expired)
    - **include_expired**: Include expired invitations in results

    Требуется заголовок: X-SuperAdmin-Token
    """
    skip = (page - 1) * size

    # Валидация параметров происходит в CRUD
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, status=status, include_expired=include_expired
    )

    pages = (total + size - 1) // size

    return InvitationListResponse(
        invitations=invitations, total=total, page=page, size=size, pages=pages
    )


@router.put("/users/limits/{phone_number}", response_model=UserStaffRead)
async def update_user_limits_by_phone_number(
    phone_number: str,
    limits_update: UserLimitsUpdate,
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Обновить лимиты пользователя по номеру телефона (только SuperAdmin).

    - **phone_number**: Номер телефона пользователя
    - **clubs**: Новый лимит клубов (опционально)
    - **sections**: Новый лимит секций (опционально)

    Требуется заголовок: X-SuperAdmin-Token

    Пример использования:
    ```
    PUT /superadmin/users/limits/+77771234567
    {
        "clubs": 5,
        "sections": 10
    }
    ```
    """
    # Все валидации и ошибки обрабатываются в CRUD
    updated_user = await update_user_limits_by_phone(db, phone_number, limits_update)
    return updated_user


@router.get("/users/limits/{phone_number}")
async def get_user_limits_by_phone_number(
    phone_number: str,
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Получить информацию о лимитах пользователя по номеру телефона.

    - **phone_number**: Номер телефона пользователя

    Требуется заголовок: X-SuperAdmin-Token
    """

    # Получаем пользователя (с валидацией в CRUD)
    user = await get_user_staff_by_phone(db, phone_number)
    if not user:

        raise NotFoundError("Staff user", f"No user found with phone {phone_number}")

    # Получаем текущее использование
    current_counts = await get_user_current_counts(db, user.id)

    user_limits = user.limits or {"clubs": 0, "sections": 0}

    return {
        "user_id": user.id,
        "phone_number": user.phone_number,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "limits": user_limits,
        "current_usage": current_counts,
        "available": {
            "clubs": max(0, user_limits.get("clubs", 0) - current_counts["clubs"]),
            "sections": max(
                0, user_limits.get("sections", 0) - current_counts["sections"]
            ),
        },
    }


@router.get("/stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Получить статистику системы (только SuperAdmin).

    Возвращает общую статистику по:
    - Приглашениям
    - Пользователям
    - Клубам
    - Секциям

    Требуется заголовок: X-SuperAdmin-Token
    """
    # Статистика приглашений
    invitation_stats = await get_invitation_stats(db)

    # Статистика пользователей
    staff_count_result = await db.execute(select(func.count(UserStaff.id)))
    staff_count = staff_count_result.scalar() or 0

    student_count_result = await db.execute(select(func.count(UserStudent.id)))
    student_count = student_count_result.scalar() or 0

    # Статистика клубов
    clubs_count_result = await db.execute(select(func.count(Club.id)))
    clubs_count = clubs_count_result.scalar() or 0

    # Статистика секций
    sections_count_result = await db.execute(select(func.count(Section.id)))
    sections_count = sections_count_result.scalar() or 0

    active_sections_result = await db.execute(
        select(func.count(Section.id)).where(Section.active == True)
    )
    active_sections_count = active_sections_result.scalar() or 0

    return {
        "invitations": invitation_stats,
        "users": {
            "total_staff": staff_count,
            "total_students": student_count,
            "total_users": staff_count + student_count,
        },
        "clubs": {
            "total_clubs": clubs_count,
        },
        "sections": {
            "total_sections": sections_count,
            "active_sections": active_sections_count,
            "inactive_sections": sections_count - active_sections_count,
        },
        "system": {
            "generated_at": "2025-06-19T12:00:00Z",  # Можно заменить на datetime.now()
            "version": "1.0.0",
        },
    }


@router.get("/users/search")
async def search_staff_users(
    query: str = Query(
        ..., min_length=3, description="Search query (min 3 characters)"
    ),
    limit: int = Query(10, ge=1, le=50, description="Maximum results to return"),
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Поиск staff пользователей по имени, фамилии или номеру телефона.

    - **query**: Поисковый запрос (минимум 3 символа)
    - **limit**: Максимальное количество результатов

    Требуется заголовок: X-SuperAdmin-Token
    """

    if len(query.strip()) < 3:
        raise ValidationError("Search query must be at least 3 characters long")

    search_term = f"%{query.strip()}%"

    result = await db.execute(
        select(UserStaff)
        .where(
            or_(
                UserStaff.first_name.ilike(search_term),
                UserStaff.last_name.ilike(search_term),
                UserStaff.phone_number.ilike(search_term),
                UserStaff.username.ilike(search_term),
            )
        )
        .limit(limit)
        .order_by(UserStaff.created_at.desc())
    )

    users = result.scalars().all()

    return {
        "query": query,
        "total_found": len(users),
        "users": [
            {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "phone_number": user.phone_number,
                "username": user.username,
                "limits": user.limits,
                "created_at": user.created_at,
            }
            for user in users
        ],
    }


@router.post("/cleanup/expired-invitations")
async def cleanup_expired_invitations(
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Очистить истекшие приглашения (старше 30 дней).

    Требуется заголовок: X-SuperAdmin-Token
    """

    # Операция и ошибки обрабатываются в CRUD
    deleted_count = await cleanup_expired_invitations(db)

    return {
        "message": f"Cleanup completed successfully",
        "deleted_invitations": deleted_count,
        "status": "success",
    }
