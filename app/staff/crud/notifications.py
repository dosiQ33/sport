from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc
from app.staff.models.notifications import StaffNotification
from app.staff.schemas.notifications import NotificationCreate
from typing import List, Optional

async def create_notification(db: AsyncSession, notification: NotificationCreate) -> StaffNotification:
    db_notification = StaffNotification(
        recipient_id=notification.recipient_id,
        title=notification.title,
        message=notification.message,
        metadata_json=notification.metadata_json
    )
    db.add(db_notification)
    await db.commit()
    await db.refresh(db_notification)
    return db_notification

async def get_my_notifications(
    db: AsyncSession, 
    user_id: int, 
    skip: int = 0, 
    limit: int = 20
) -> List[StaffNotification]:
    query = (
        select(StaffNotification)
        .where(StaffNotification.recipient_id == user_id)
        .order_by(desc(StaffNotification.created_at))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(query)
    return result.scalars().all()

async def get_unread_count(db: AsyncSession, user_id: int) -> int:
    query = (
        select(func.count(StaffNotification.id))
        .where(StaffNotification.recipient_id == user_id)
        .where(StaffNotification.is_read == False)
    )
    result = await db.execute(query)
    return result.scalar() or 0

async def mark_notification_as_read(db: AsyncSession, notification_id: int, user_id: int) -> Optional[StaffNotification]:
    query = (
        update(StaffNotification)
        .where(StaffNotification.id == notification_id)
        .where(StaffNotification.recipient_id == user_id)
        .values(is_read=True)
        .returning(StaffNotification)
    )
    result = await db.execute(query)
    await db.commit()
    return result.scalar_one_or_none()

async def mark_all_as_read(db: AsyncSession, user_id: int) -> None:
    query = (
        update(StaffNotification)
        .where(StaffNotification.recipient_id == user_id)
        .where(StaffNotification.is_read == False)
        .values(is_read=True)
    )
    await db.execute(query)
    await db.commit()
