from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.staff.schemas.invitations import (
    InvitationCreateByOwner,
    InvitationRead,
    InvitationListResponse,
)

from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.invitations import (
    create_invitation_by_owner,
    get_invitations_paginated,
    get_invitation_by_id,
    delete_invitation,
    get_invitation_stats,
)

router = APIRouter(prefix="/invitations", tags=["Invitations"])


@router.post("/club/{club_id}", response_model=InvitationRead)
@limiter.limit("10/hour")
async def create_club_staff_invitation(
    request: Request,
    club_id: int,
    invitation: InvitationCreateByOwner,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Создать приглашение для staff в клуб (только владелец клуба).

    - **phone_number**: Номер телефона приглашаемого
    - **role**: Роль (admin/coach)

    Владельцы не могут приглашать других владельцев.
    """
    # Получаем пользователя
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    try:
        db_invitation = await create_invitation_by_owner(
            db, invitation, user_staff.id, club_id
        )
        return db_invitation
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/my", response_model=InvitationListResponse)
@limiter.limit("30/minute")
async def get_my_invitations(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    is_used: Optional[bool] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить приглашения, созданные текущим пользователем.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    skip = (page - 1) * size
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, created_by_id=user_staff.id, is_used=is_used
    )

    pages = (total + size - 1) // size

    return InvitationListResponse(
        invitations=invitations, total=total, page=page, size=size, pages=pages
    )


@router.get("/club/{club_id}", response_model=InvitationListResponse)
@limiter.limit("30/minute")
async def get_club_invitations(
    request: Request,
    club_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    is_used: Optional[bool] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить все приглашения для конкретного клуба.
    Доступно только владельцу клуба.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    # Проверяем права доступа
    from app.staff.crud.clubs import check_user_club_permission

    has_permission = await check_user_club_permission(db, user_staff.id, club_id)
    if not has_permission:
        raise HTTPException(status_code=403, detail="Access denied")

    skip = (page - 1) * size
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, club_id=club_id, is_used=is_used
    )

    pages = (total + size - 1) // size

    return InvitationListResponse(
        invitations=invitations, total=total, page=page, size=size, pages=pages
    )


@router.get("/{invitation_id}", response_model=InvitationRead)
@limiter.limit("30/minute")
async def get_invitation(
    request: Request,
    invitation_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить информацию о приглашении по ID.
    """
    invitation = await get_invitation_by_id(db, invitation_id)
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found")

    # Проверяем права доступа
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    # Можно видеть только свои приглашения или если есть права на клуб
    if invitation.created_by_id != user_staff.id:
        if invitation.club_id:
            from app.staff.crud.clubs import check_user_club_permission

            has_permission = await check_user_club_permission(
                db, user_staff.id, invitation.club_id
            )
            if not has_permission:
                raise HTTPException(status_code=403, detail="Access denied")
        else:
            raise HTTPException(status_code=403, detail="Access denied")

    return invitation


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("10/minute")
async def delete_invitation_route(
    request: Request,
    invitation_id: int,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Удалить приглашение (только создатель).
    Нельзя удалить использованное приглашение.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    try:
        deleted = await delete_invitation(db, invitation_id, user_staff.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Invitation not found")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/stats/my")
@limiter.limit("20/minute")
async def get_my_invitation_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить статистику по своим приглашениям.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise HTTPException(status_code=404, detail="Staff user not found")

    stats = await get_invitation_stats(db, created_by_id=user_staff.id)
    return stats
