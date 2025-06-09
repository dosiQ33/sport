# app/superAdmin/core/jwt_auth.py
import jwt
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from fastapi import HTTPException, status
import logging

logger = logging.getLogger(__name__)


class JWTManager:
    def __init__(self):
        # Use a strong secret key from environment
        self.secret_key = os.getenv("JWT_SECRET_KEY")
        self.algorithm = "HS256"
        self.access_token_expire_minutes = int(
            os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES")
        )

        # Super admin credentials from environment
        self.super_admin_username = os.getenv("SUPER_ADMIN_USERNAME")
        self.super_admin_password = os.getenv("SUPER_ADMIN_PASSWORD")

    def verify_super_admin_credentials(self, username: str, password: str) -> bool:
        """Verify super admin credentials"""
        return (
            username == self.super_admin_username
            and password == self.super_admin_password
        )

    def create_access_token(
        self, phone_number: str, role: str, extra_data: Dict[str, Any] = None
    ) -> str:
        """
        Create JWT access token with phone number and role

        Args:
            phone_number: User's phone number
            role: User's role (coach, manager, admin, owner)
            extra_data: Additional data to include in token

        Returns:
            JWT token string
        """
        try:
            # Calculate expiration time
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=self.access_token_expire_minutes
            )

            # Create payload
            payload = {
                "phone_number": phone_number,
                "role": role,
                "exp": expire,
                "iat": datetime.now(timezone.utc),
                "type": "access_token",
            }

            # Add extra data if provided
            if extra_data:
                payload.update(extra_data)

            # Generate token
            token = jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

            logger.info(f"JWT token created for phone: {phone_number}, role: {role}")
            return token

        except Exception as e:
            logger.error(f"Failed to create JWT token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create access token",
            )

    def decode_token(self, token: str) -> Dict[str, Any]:
        """
        Decode and verify JWT token

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            # Decode token
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])

            # Verify token type
            if payload.get("type") != "access_token":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                )

            # Token is valid
            logger.info(f"JWT token decoded for phone: {payload.get('phone_number')}")
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            logger.warning("Invalid JWT token provided")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except Exception as e:
            logger.error(f"Unexpected error decoding JWT token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token validation failed",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def get_token_info(self, token: str) -> Dict[str, Any]:
        """
        Get token information without strict validation (for debugging)

        Args:
            token: JWT token string

        Returns:
            Token payload or error info
        """
        try:
            # Decode without verification for debugging
            payload = jwt.decode(token, options={"verify_signature": False})
            return {
                "valid": True,
                "payload": payload,
                "expired": payload.get("exp", 0)
                < datetime.now(timezone.utc).timestamp(),
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}


# Create global instance
jwt_manager = JWTManager()
