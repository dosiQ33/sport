"""Student Payment Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class PaymentStatusEnum(str, Enum):
    """Payment status"""
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    cancelled = "cancelled"


class PaymentMethodEnum(str, Enum):
    """Payment method"""
    card = "card"
    kaspi = "kaspi"
    cash = "cash"
    transfer = "transfer"


class PaymentRecordRead(BaseModel):
    """Payment record for display"""
    id: int
    
    # Club info
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    
    # Amount
    amount: float
    currency: str = "KZT"
    
    # Status and method
    status: PaymentStatusEnum
    payment_method: Optional[PaymentMethodEnum] = None
    
    # Description
    description: Optional[str] = None
    tariff_name: Optional[str] = None
    
    # Date
    payment_date: Optional[datetime] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class PaymentListResponse(BaseModel):
    """Response with payment list"""
    payments: List[PaymentRecordRead]
    total: int
    page: int = 1
    size: int = 20
    pages: int = 1


class InitiatePaymentRequest(BaseModel):
    """Request to initiate payment"""
    club_id: int
    tariff_id: int
    group_id: Optional[int] = None
    payment_method: PaymentMethodEnum = PaymentMethodEnum.card
    
    class Config:
        json_schema_extra = {
            "example": {
                "club_id": 1,
                "tariff_id": 1,
                "group_id": 1,
                "payment_method": "card"
            }
        }


class InitiatePaymentResponse(BaseModel):
    """Response with payment initiation details"""
    payment_id: int
    amount: float
    currency: str = "KZT"
    status: PaymentStatusEnum
    redirect_url: Optional[str] = None
    external_id: Optional[str] = None


class PaymentStatsResponse(BaseModel):
    """Payment statistics"""
    total_paid: float = 0
    pending_payments: int = 0
    payments_this_month: int = 0
    amount_this_month: float = 0
