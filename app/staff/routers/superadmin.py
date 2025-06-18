from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_session
from app.staff.schemas.invitations import (
    InvitationCreateBySuperAdmin,
    InvitationRead,
    InvitationListResponse,
)
from app.staff.schemas.users import UserLimitsUpdate, UserStaffRead
from app.staff.crud.invitations import (
    create_invitation_by_superadmin,
    get_invitations_paginated,
    get_invitation_stats,
)
from app.staff.crud.users import update_user_limits_by_phone
from app.core.dependencies import verify_superadmin_token

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

    Требуется заголовок: X-SuperAdmin-Token
    """
    if invitation.role != "owner":
        raise HTTPException(
            status_code=400, detail="SuperAdmin can only create invitations for owners"
        )

    try:
        # Создаем приглашение без created_by_id (система)
        db_invitation = await create_invitation_by_superadmin(
            db, invitation, created_by_type="superadmin"
        )
        return db_invitation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/invitations", response_model=InvitationListResponse)
async def get_all_invitations(
    page: int = 1,
    size: int = 20,
    is_used: Optional[bool] = None,
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Получить все приглашения (только SuperAdmin).

    Требуется заголовок: X-SuperAdmin-Token
    """
    skip = (page - 1) * size
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, is_used=is_used
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
    try:
        updated_user = await update_user_limits_by_phone(
            db, phone_number, limits_update
        )
        return updated_user
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to update user limits")


@router.get("/stats")
async def get_system_stats(
    db: AsyncSession = Depends(get_session),
    is_superadmin: bool = Depends(verify_superadmin_token),
):
    """
    Получить статистику системы (только SuperAdmin).

    Требуется заголовок: X-SuperAdmin-Token
    """
    invitation_stats = await get_invitation_stats(db)

    # Можно добавить больше статистики
    return {
        "invitations": invitation_stats,
        # Добавьте другую статистику по необходимости
    }
