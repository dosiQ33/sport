"""Student Payments Router - Endpoints for payment history and initiation"""
import math
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_student_user
from app.core.exceptions import NotFoundError
from app.students.crud.users import get_user_student_by_telegram_id
from app.students.crud.payments import (
    get_student_payments,
    initiate_payment,
    get_payment_stats,
    complete_payment,
)
from app.students.schemas.payments import (
    PaymentRecordRead,
    PaymentListResponse,
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    PaymentStatsResponse,
    CompletePaymentRequest,
    CompletePaymentResponse,
)

router = APIRouter(prefix="/students/payments", tags=["Student Payments"])


@router.get("/", response_model=PaymentListResponse)
@limiter.limit("30/minute")
async def get_my_payments(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get payment history.
    
    Returns paginated list of payment records.
    Optionally filter by status (pending, paid, failed, refunded, cancelled).
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    skip = (page - 1) * size
    payments, total = await get_student_payments(
        db, student.id, skip, size, status_filter
    )
    
    pages = math.ceil(total / size) if total > 0 else 1
    
    return PaymentListResponse(
        payments=payments,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.post("/initiate", response_model=InitiatePaymentResponse)
@limiter.limit("5/minute")
async def initiate_new_payment(
    request: Request,
    payment_request: InitiatePaymentRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Initiate a new payment for a membership.
    
    Creates a pending payment record and returns payment details.
    In production, this would integrate with a payment gateway.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    result = await initiate_payment(db, student.id, payment_request)
    
    return result


@router.get("/stats", response_model=PaymentStatsResponse)
@limiter.limit("30/minute")
async def get_my_payment_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get payment statistics.
    
    Returns total paid, pending payments, payments this month, etc.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return PaymentStatsResponse()
    
    stats = await get_payment_stats(db, student.id)
    
    return stats


@router.post("/complete", response_model=CompletePaymentResponse)
@limiter.limit("10/minute")
async def complete_my_payment(
    request: Request,
    payment_request: CompletePaymentRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Complete a payment and activate membership.
    
    This is a mock endpoint that simulates successful payment completion.
    In production, this would be replaced by payment gateway webhook.
    
    - Marks the payment as paid
    - Creates or extends student enrollment in the club
    - Returns enrollment details
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    result = await complete_payment(db, student.id, payment_request.payment_id)
    
    return result
