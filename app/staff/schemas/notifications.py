from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, Any, Dict

class NotificationBase(BaseModel):
    title: str
    message: str
    metadata_json: Optional[Dict[str, Any]] = None

class NotificationCreate(NotificationBase):
    recipient_id: int

class NotificationRead(NotificationBase):
    id: int
    recipient_id: int
    is_read: bool
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)
