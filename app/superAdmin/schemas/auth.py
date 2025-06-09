# app/superAdmin/schemas/auth.py
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, Literal

# Define role types
RoleType = Literal["coach", "manager", "admin", "owner"]


class SuperAdminLogin(BaseModel):
    """Super admin login credentials"""

    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6, max_length=100)


class TokenRequest(BaseModel):
    """Request to generate JWT token"""

    phone_number: str = Field(
        ..., min_length=10, max_length=30, description="Phone number of the user"
    )
    role: RoleType = Field(..., description="Role to assign to the token")
    extra_data: Optional[Dict[str, Any]] = Field(
        default=None, description="Additional data to include in token (optional)"
    )
    expires_in_minutes: Optional[int] = Field(
        default=60,
        ge=1,
        le=1440,  # Max 24 hours
        description="Token expiration time in minutes (default: 60, max: 1440)",
    )


class TokenResponse(BaseModel):
    """JWT token response"""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds
    phone_number: str
    role: str


class TokenDecodeResponse(BaseModel):
    """Token decode response"""

    phone_number: str
    role: str
    expires_at: int  # Unix timestamp
    issued_at: int  # Unix timestamp
    extra_data: Optional[Dict[str, Any]] = None


class TokenInfoResponse(BaseModel):
    """Token information response (for debugging)"""

    valid: bool
    payload: Optional[Dict[str, Any]] = None
    expired: Optional[bool] = None
    error: Optional[str] = None
