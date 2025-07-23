import hashlib
import hmac
import json
import urllib.parse
from urllib.parse import unquote_plus
import logging
from typing import Dict, Any
from datetime import datetime, timezone
from fastapi import HTTPException, status

from app.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


class TelegramAuthError(Exception):
    """Custom exception for Telegram authentication errors"""

    def __init__(self, message: str, error_code: str = "AUTH_ERROR"):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class TelegramAuth:
    def __init__(self, bot_token: str):
        if not bot_token:
            raise ValidationError("Bot token is required")
        self.bot_token = bot_token
        self.secret_key = hashlib.sha256(bot_token.encode()).digest()

    def validate_auth_date(self, auth_date: str, max_age_seconds: int = 86400) -> bool:
        """Validate that auth_date is not too old (default: 24 hours)"""
        try:
            if not auth_date:
                return False

            auth_timestamp = int(auth_date)
            current_timestamp = int(datetime.now(timezone.utc).timestamp())

            return current_timestamp - auth_timestamp <= max_age_seconds
        except (ValueError, TypeError):
            return False

    def validate_telegram_query(self, raw_query: str) -> Dict[str, Any]:
        """
        Validate *any* Telegram Mini-App query string
        (initData or contact) and return a parsed dict.
        """
        try:
            if not raw_query or not raw_query.strip():
                raise TelegramAuthError("Empty query data", "EMPTY_DATA")

            # Parse query string
            params = dict(urllib.parse.parse_qsl(raw_query, keep_blank_values=False))

            # Extract and validate hash
            their_hash = params.pop("hash", None)
            if not their_hash:
                raise TelegramAuthError("Hash parameter missing", "NO_HASH")

            # Step 1: build data-check-string
            data_list = [f"{k}={params[k]}" for k in sorted(params)]
            data_check_string = "\n".join(data_list)

            # Step 2: calculate our own hash
            secret_key = hmac.new(
                b"WebAppData", self.bot_token.encode(), hashlib.sha256
            ).digest()

            calc_hash = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()

            if calc_hash != their_hash:
                raise TelegramAuthError("Telegram signature mismatch", "INVALID_HASH")

            # Step 3: JSON-decode large fields **after** the verification
            if "user" in params:
                try:
                    params["user"] = json.loads(unquote_plus(params["user"]))
                except json.JSONDecodeError:
                    raise TelegramAuthError(
                        "Invalid user data format", "INVALID_USER_DATA"
                    )

            if "contact" in params:
                try:
                    params["contact"] = json.loads(unquote_plus(params["contact"]))
                except json.JSONDecodeError:
                    raise TelegramAuthError(
                        "Invalid contact data format", "INVALID_CONTACT_DATA"
                    )

            return params

        except TelegramAuthError:
            raise
        except Exception as e:
            logger.error("Query validation error occurred")
            raise TelegramAuthError("Query validation failed", "VALIDATION_ERROR")

    def authenticate(self, init_data: str) -> Dict[str, Any]:
        """
        Full authentication process with secure error handling
        """
        try:
            # Basic validation
            if not init_data or not init_data.strip():
                raise TelegramAuthError("Authentication data required", "MISSING_DATA")

            # Use the new validation method
            parsed_data = self.validate_telegram_query(init_data)

            # Validate auth_date
            if "auth_date" not in parsed_data:
                raise TelegramAuthError(
                    "Authentication timestamp missing", "NO_AUTH_DATE"
                )

            if not self.validate_auth_date(parsed_data["auth_date"]):
                raise TelegramAuthError("Authentication expired", "EXPIRED_AUTH")

            # Validate user data (if present)
            if "user" in parsed_data and parsed_data["user"]:
                user_data = parsed_data["user"]

                # Validate required user fields
                required_fields = ["id", "first_name"]
                for field in required_fields:
                    if field not in user_data:
                        raise TelegramAuthError(
                            "Incomplete user data", "INCOMPLETE_USER_DATA"
                        )

            return parsed_data

        except TelegramAuthError as e:
            logger.warning(f"Telegram auth failed with code: {e.error_code}")
            # Always return generic error to client
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "tma"},
            )
        except Exception as e:
            logger.error("Unexpected authentication error occurred")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication failed",
                headers={"WWW-Authenticate": "tma"},
            )

    def authenticate_contact_request(self, init_data: str) -> Dict[str, Any]:
        """
        Специальный метод для аутентификации запросов с contact данными
        """
        try:
            parsed_data = self.validate_telegram_query(init_data)

            if "contact" not in parsed_data:
                raise TelegramAuthError("Contact data missing", "NO_CONTACT_DATA")

            contact_data = parsed_data["contact"]

            required_contact_fields = ["phone_number", "first_name"]
            for field in required_contact_fields:
                if field not in contact_data:
                    raise TelegramAuthError(
                        f"Contact field missing", "INCOMPLETE_CONTACT_DATA"
                    )

            return parsed_data

        except TelegramAuthError as e:
            logger.warning(f"Contact auth failed with code: {e.error_code}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Contact authentication failed",
                headers={"WWW-Authenticate": "tma"},
            )
        except Exception as e:
            logger.error("Unexpected contact authentication error occurred")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Contact authentication failed",
                headers={"WWW-Authenticate": "tma"},
            )
