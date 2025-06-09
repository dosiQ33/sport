# app/superAdmin/routers/auth.py
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.superAdmin.core.jwt_auth import jwt_manager
from app.superAdmin.schemas.auth import (
    SuperAdminLogin,
    TokenRequest,
    TokenResponse,
    TokenDecodeResponse,
    TokenInfoResponse,
)
from app.core.limits import limiter

router = APIRouter(prefix="/auth", tags=["Super Admin Auth"])

# Security scheme for JWT tokens
security = HTTPBearer()


@router.post("/generate-token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def generate_jwt_token(
    request: Request, token_request: TokenRequest, credentials: SuperAdminLogin
):
    """
    Generate JWT token for specified phone number and role.
    Requires super admin credentials.

    This endpoint allows super admin to create tokens for any user with any role.
    """
    # Verify super admin credentials
    if not jwt_manager.verify_super_admin_credentials(
        credentials.username, credentials.password
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid super admin credentials",
        )

    # Update JWT manager expiration if custom time provided
    if token_request.expires_in_minutes:
        original_expire = jwt_manager.access_token_expire_minutes
        jwt_manager.access_token_expire_minutes = token_request.expires_in_minutes

    try:
        # Generate token
        access_token = jwt_manager.create_access_token(
            phone_number=token_request.phone_number,
            role=token_request.role,
            extra_data=token_request.extra_data,
        )

        return TokenResponse(
            access_token=access_token,
            expires_in=token_request.expires_in_minutes * 60,  # Convert to seconds
            phone_number=token_request.phone_number,
            role=token_request.role,
        )

    finally:
        # Reset original expiration time
        if token_request.expires_in_minutes:
            jwt_manager.access_token_expire_minutes = original_expire


@router.post("/decode-token", response_model=TokenDecodeResponse)
@limiter.limit("20/minute")
async def decode_jwt_token(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Decode JWT token and return its contents.
    Provide token in Authorization header as 'Bearer <token>'.
    """
    token = credentials.credentials
    payload = jwt_manager.decode_token(token)

    # Extract data from payload
    extra_data = {
        k: v
        for k, v in payload.items()
        if k not in ["phone_number", "role", "exp", "iat", "type"]
    }

    return TokenDecodeResponse(
        phone_number=payload["phone_number"],
        role=payload["role"],
        expires_at=payload["exp"],
        issued_at=payload["iat"],
        extra_data=extra_data if extra_data else None,
    )


@router.post("/token-info", response_model=TokenInfoResponse)
@limiter.limit("20/minute")
async def get_token_info(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get token information (for debugging).
    This endpoint doesn't validate the token signature, useful for checking expired tokens.
    """
    token = credentials.credentials
    info = jwt_manager.get_token_info(token)

    return TokenInfoResponse(**info)


@router.post("/verify-token", response_model=dict)
@limiter.limit("30/minute")
async def verify_jwt_token(
    request: Request, credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Verify if JWT token is valid and not expired.
    Returns basic verification status.
    """
    token = credentials.credentials

    try:
        payload = jwt_manager.decode_token(token)
        return {
            "valid": True,
            "phone_number": payload["phone_number"],
            "role": payload["role"],
            "message": "Token is valid",
        }
    except HTTPException as e:
        return {"valid": False, "message": e.detail}
