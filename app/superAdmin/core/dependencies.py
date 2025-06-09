# app/superAdmin/core/dependencies.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.superAdmin.core.jwt_auth import jwt_manager
from typing import Dict, Any, List, Optional

# Security scheme for JWT tokens
jwt_security = HTTPBearer(scheme_name="JWT Token", description="Enter your JWT token")


async def get_current_user_from_jwt(
    credentials: HTTPAuthorizationCredentials = Depends(jwt_security),
) -> Dict[str, Any]:
    """
    Dependency to get current user from JWT token.
    Returns decoded token payload containing phone_number, role, and other data.

    Usage in route:
    @app.get("/protected")
    async def protected_route(user: Dict = Depends(get_current_user_from_jwt)):
        phone_number = user["phone_number"]
        role = user["role"]
        return {"message": f"Hello {phone_number} with role {role}"}
    """
    token = credentials.credentials
    return jwt_manager.decode_token(token)


async def get_current_user_phone(
    user: Dict[str, Any] = Depends(get_current_user_from_jwt),
) -> str:
    """
    Dependency to get current user's phone number from JWT token.

    Usage:
    async def my_route(phone: str = Depends(get_current_user_phone)):
        return {"your_phone": phone}
    """
    return user["phone_number"]


async def get_current_user_role(
    user: Dict[str, Any] = Depends(get_current_user_from_jwt),
) -> str:
    """
    Dependency to get current user's role from JWT token.

    Usage:
    async def my_route(role: str = Depends(get_current_user_role)):
        return {"your_role": role}
    """
    return user["role"]


def require_roles(allowed_roles: List[str]):
    """
    Dependency factory to require specific roles.

    Usage:
    @app.get("/admin-only")
    async def admin_route(user: Dict = Depends(require_roles(["admin", "owner"]))):
        return {"message": "You have admin access"}
    """

    async def role_dependency(
        user: Dict[str, Any] = Depends(get_current_user_from_jwt),
    ) -> Dict[str, Any]:
        user_role = user.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}. Your role: {user_role}",
            )
        return user

    return role_dependency


def require_phone_access(target_phone: Optional[str] = None):
    """
    Dependency factory to require access to specific phone number.
    User can access their own data or admin/owner can access anyone's data.

    Usage:
    @app.get("/users/{phone}/data")
    async def get_user_data(
        phone: str,
        user: Dict = Depends(require_phone_access())
    ):
        # Will check if user can access data for the phone number
        return {"data": "sensitive data"}
    """

    async def phone_access_dependency(
        user: Dict[str, Any] = Depends(get_current_user_from_jwt),
    ) -> Dict[str, Any]:
        user_phone = user.get("phone_number")
        user_role = user.get("role")

        # Admin and owner can access any phone
        if user_role in ["admin", "owner"]:
            return user

        # Users can only access their own phone data
        if target_phone and user_phone != target_phone:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You can only access your own data.",
            )

        return user

    return phone_access_dependency


# Convenience dependencies for common roles
require_owner = require_roles(["owner"])
require_admin = require_roles(["admin", "owner"])
require_manager = require_roles(["manager", "admin", "owner"])
require_coach = require_roles(["coach", "manager", "admin", "owner"])
