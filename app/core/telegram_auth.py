import hashlib
import hmac
import json
import urllib.parse
from urllib.parse import unquote_plus
import logging
from typing import Dict, Any
from datetime import datetime, timezone

from .exceptions import TelegramAuthError

logger = logging.getLogger(__name__)


class TelegramAuth:
    def __init__(self, bot_token: str):
        if not bot_token:
            raise ValueError("Bot token is required")
        self.bot_token = bot_token
        self.secret_key = hashlib.sha256(bot_token.encode()).digest()

    def parse_init_data(self, init_data: str) -> Dict[str, Any]:
        """Parse Telegram initData string into dictionary"""
        try:
            if not init_data or not init_data.strip():
                raise TelegramAuthError("Empty init data", "EMPTY_DATA")

            parsed = urllib.parse.parse_qs(init_data)
            result = {}

            for key, value in parsed.items():
                if len(value) == 1:
                    if key == "user":
                        try:
                            result[key] = json.loads(unquote_plus(value[0]))
                        except json.JSONDecodeError:
                            raise TelegramAuthError(
                                "Invalid user data format", "INVALID_USER_DATA"
                            )
                    elif key == "contact":
                        try:
                            result[key] = json.loads(unquote_plus(value[0]))
                        except json.JSONDecodeError:
                            raise TelegramAuthError(
                                "Invalid contact data format", "INVALID_CONTACT_DATA"
                            )
                    elif key in ["auth_date", "query_id"]:
                        result[key] = value[0]
                    else:
                        result[key] = value[0]
                else:
                    result[key] = value

            return result
        except TelegramAuthError:
            raise
        except Exception as e:
            # Логируем только общую ошибку без деталей
            logger.error("Failed to parse init data")
            raise TelegramAuthError("Invalid data format", "PARSE_ERROR")

    def validate_hash(self, init_data: str) -> bool:
        """Validate Telegram initData hash according to official docs"""
        try:
            parsed_data = urllib.parse.parse_qs(init_data)

            if "hash" not in parsed_data:
                raise TelegramAuthError("Missing authentication hash", "NO_HASH")

            received_hash = parsed_data["hash"][0]
            if not received_hash:
                raise TelegramAuthError("Empty authentication hash", "EMPTY_HASH")

            # Remove hash from data for validation
            data_check_string_parts = []
            for key, value in parsed_data.items():
                if key != "hash" and value and value[0]:
                    data_check_string_parts.append(f"{key}={value[0]}")

            if not data_check_string_parts:
                raise TelegramAuthError("No data to validate", "NO_DATA")

            # Sort alphabetically
            data_check_string_parts.sort()
            data_check_string = "\n".join(data_check_string_parts)

            # Create HMAC
            secret_key = hmac.new(
                "WebAppData".encode(), self.bot_token.encode(), hashlib.sha256
            ).digest()

            calculated_hash = hmac.new(
                secret_key, data_check_string.encode(), hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(received_hash, calculated_hash)

        except TelegramAuthError:
            raise
        except Exception as e:
            logger.error("Hash validation error occurred")
            raise TelegramAuthError("Hash validation failed", "HASH_VALIDATION_ERROR")

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

            # Return the complete parsed data (including contact if present)
            return parsed_data

        except TelegramAuthError as e:
            # Логируем только код ошибки, без деталей
            logger.warning(f"Telegram auth failed with code: {e.error_code}")
            # Re-raise as TelegramAuthError instead of HTTPException
            raise e
        except Exception as e:
            # Логируем факт ошибки без деталей
            logger.error("Unexpected authentication error occurred")
            raise TelegramAuthError("Authentication failed", "UNEXPECTED_ERROR")

    def authenticate_contact_request(self, init_data: str) -> Dict[str, Any]:
        """
        Специальный метод для аутентификации запросов с contact данными
        """
        try:
            # Используем новый валидатор
            parsed_data = self.validate_telegram_query(init_data)

            # Проверяем наличие contact данных
            if "contact" not in parsed_data:
                raise TelegramAuthError("Contact data missing", "NO_CONTACT_DATA")

            contact_data = parsed_data["contact"]

            # Валидируем обязательные поля contact
            required_contact_fields = ["phone_number", "first_name"]
            for field in required_contact_fields:
                if field not in contact_data:
                    raise TelegramAuthError(
                        f"Contact field missing", "INCOMPLETE_CONTACT_DATA"
                    )

            return parsed_data

        except TelegramAuthError as e:
            logger.warning(f"Contact auth failed with code: {e.error_code}")
            # Re-raise as TelegramAuthError instead of HTTPException
            raise e
        except Exception as e:
            logger.error("Unexpected contact authentication error occurred")
            raise TelegramAuthError("Contact authentication failed", "UNEXPECTED_ERROR")
