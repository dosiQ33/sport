from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.staff.schemas.invitations import (
    InvitationCreateByOwner,
    InvitationRead,
    InvitationListResponse,
    InvitationAccept,
    InvitationDecline,
    InvitationActionResponse,
    PendingInvitationsResponse,
    PendingInvitationRead,
)
from app.staff.models.invitations import InvitationStatus

from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.invitations import (
    create_invitation_by_owner,
    get_invitations_paginated,
    get_invitation_by_id,
    delete_invitation,
    get_invitation_stats,
    accept_invitation,
    decline_invitation,
    get_pending_invitations_by_user_id,
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
        raise NotFoundError("Staff user")

    # Все проверки прав и ошибки обрабатываются в CRUD
    db_invitation = await create_invitation_by_owner(
        db, invitation, user_staff.id, club_id
    )
    return db_invitation


# НОВЫЕ ENDPOINTS ДЛЯ РАБОТЫ С ОТВЕТАМИ НА ПРИГЛАШЕНИЯ


@router.get("/my-pending", response_model=PendingInvitationsResponse)
@limiter.limit("60/minute")
async def get_my_pending_invitations(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить все ожидающие приглашения для текущего пользователя.

    Показывает приглашения, на которые пользователь может ответить (принять/отклонить).
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Получаем ожидающие приглашения
    pending_invitations = await get_pending_invitations_by_user_id(db, user_staff.id)

    # Преобразуем в схему ответа
    pending_reads = []
    expiring_soon_count = 0
    now = datetime.now(timezone.utc)

    for invitation in pending_invitations:
        days_until_expiry = (invitation.expires_at - now).days
        if days_until_expiry <= 3:
            expiring_soon_count += 1

        pending_read = PendingInvitationRead(
            id=invitation.id,
            role=invitation.role,
            club_id=invitation.club_id,
            expires_at=invitation.expires_at,
            created_at=invitation.created_at,
            club=invitation.club,
            created_by=invitation.created_by,
            created_by_type=invitation.created_by_type,
            days_until_expiry=max(0, days_until_expiry),
        )
        pending_reads.append(pending_read)

    return PendingInvitationsResponse(
        invitations=pending_reads,
        total=len(pending_reads),
        expiring_soon=expiring_soon_count,
    )


@router.post("/{invitation_id}/accept", response_model=InvitationActionResponse)
@limiter.limit("10/minute")
async def accept_pending_invitation(
    request: Request,
    invitation_id: int,
    invitation_accept: InvitationAccept,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Принять приглашение.

    При принятии автоматически создается запись в user_roles для соответствующего клуба.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Принимаем приглашение (все проверки в CRUD)
    invitation = await accept_invitation(db, invitation_id, user_staff.id)

    return InvitationActionResponse(
        id=invitation.id,
        status=invitation.status,
        message=f"Invitation accepted successfully! You are now {invitation.role.value} in {invitation.club.name if invitation.club else 'the system'}.",
        club_id=invitation.club_id,
        club_name=invitation.club.name if invitation.club else None,
        role=invitation.role,
    )


@router.post("/{invitation_id}/decline", response_model=InvitationActionResponse)
@limiter.limit("10/minute")
async def decline_pending_invitation(
    request: Request,
    invitation_id: int,
    invitation_decline: InvitationDecline,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Отклонить приглашение.

    - **reason**: Причина отклонения (опционально)
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Отклоняем приглашение (все проверки в CRUD)
    invitation = await decline_invitation(
        db, invitation_id, user_staff.id, invitation_decline.reason
    )

    return InvitationActionResponse(
        id=invitation.id,
        status=invitation.status,
        message=f"Invitation declined.",
        club_id=invitation.club_id,
        club_name=invitation.club.name if invitation.club else None,
        role=invitation.role,
    )


# СУЩЕСТВУЮЩИЕ ENDPOINTS (обновленные)


@router.get("/my", response_model=InvitationListResponse)
@limiter.limit("30/minute")
async def get_my_invitations(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[InvitationStatus] = Query(
        None, description="Filter by invitation status"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить приглашения, созданные текущим пользователем.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    skip = (page - 1) * size

    # Валидация параметров происходит в CRUD
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, created_by_id=user_staff.id, status=status
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
    status: Optional[InvitationStatus] = Query(
        None, description="Filter by invitation status"
    ),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Получить все приглашения для конкретного клуба.
    Доступно только владельцу клуба.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Проверяем права доступа
    from app.staff.crud.clubs import check_user_club_permission

    has_permission = await check_user_club_permission(db, user_staff.id, club_id)
    if not has_permission:
        raise PermissionDeniedError("view", "club invitations")

    skip = (page - 1) * size

    # Валидация параметров происходит в CRUD
    invitations, total = await get_invitations_paginated(
        db, skip=skip, limit=size, club_id=club_id, status=status
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
    # Получаем приглашение (с проверкой существования)
    invitation = await get_invitation_by_id(db, invitation_id)

    # Проверяем права доступа
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Можно видеть только свои приглашения или если есть права на клуб
    if invitation.created_by_id != user_staff.id:
        if invitation.club_id:
            from app.staff.crud.clubs import check_user_club_permission

            has_permission = await check_user_club_permission(
                db, user_staff.id, invitation.club_id
            )
            if not has_permission:
                raise PermissionDeniedError("view", "invitation")
        else:
            raise PermissionDeniedError("view", "invitation")

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
    Нельзя удалить обработанное приглашение.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Все проверки прав и ошибки обрабатываются в CRUD
    await delete_invitation(db, invitation_id, user_staff.id)
    # FastAPI автоматически вернет 204 No Content


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
        raise NotFoundError("Staff user")

    # Валидация происходит в CRUD
    stats = await get_invitation_stats(db, created_by_id=user_staff.id)
    return stats
