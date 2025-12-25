from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from app.core.database import get_session
from app.core.dependencies import get_current_staff_user
from app.staff.crud import notifications as crud_notifications
from app.staff.crud import invitations as crud_invitations
from app.staff.schemas.notifications import NotificationRead

router = APIRouter(prefix="/staff/notifications", tags=["Staff Notifications"])

@router.get("", response_model=List[NotificationRead])
async def get_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    telegram_data: dict = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    telegram_id = telegram_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Invalid Telegram ID")

    # Get staff user
    staff = await crud_invitations.get_user_staff_by_telegram_id(db, telegram_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    return await crud_notifications.get_my_notifications(db, staff.id, skip, limit)

@router.get("/unread-count", response_model=int)
async def get_unread_count(
    telegram_data: dict = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    telegram_id = telegram_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Invalid Telegram ID")

    staff = await crud_invitations.get_user_staff_by_telegram_id(db, telegram_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    return await crud_notifications.get_unread_count(db, staff.id)

@router.post("/{notification_id}/read", response_model=NotificationRead)
async def mark_as_read(
    notification_id: int,
    telegram_data: dict = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    telegram_id = telegram_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Invalid Telegram ID")

    staff = await crud_invitations.get_user_staff_by_telegram_id(db, telegram_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    updated = await crud_notifications.mark_notification_as_read(db, notification_id, staff.id)
    if not updated:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    return updated

@router.post("/read-all")
async def mark_all_as_read(
    telegram_data: dict = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    telegram_id = telegram_data.get("id")
    if not telegram_id:
        raise HTTPException(status_code=400, detail="Invalid Telegram ID")

    staff = await crud_invitations.get_user_staff_by_telegram_id(db, telegram_id)
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")

    await crud_notifications.mark_all_as_read(db, staff.id)
    return {"status": "ok"}
