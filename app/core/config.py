import os

# Настройки PostgreSQL
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mydatabase")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "db")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DATABASE_URL = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# Настройки Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUPERADMIN_TOKEN = os.getenv("SUPERADMIN_TOKEN")

# Настройки среды
ENVIRONMENT = os.getenv("ENVIRONMENT", "production").lower()
DEBUG = ENVIRONMENT in ["development", "dev"]

# Настройки retry для базы данных
DB_RETRY_ATTEMPTS = int(os.getenv("DB_RETRY_ATTEMPTS", "3"))
DB_RETRY_DELAY = float(os.getenv("DB_RETRY_DELAY", "1.0"))
DB_RETRY_BACKOFF_FACTOR = float(os.getenv("DB_RETRY_BACKOFF_FACTOR", "2.0"))

# Настройки логирования
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO" if not DEBUG else "DEBUG")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if not DEBUG else "text")

# Настройки приложения
APP_NAME = os.getenv("APP_NAME", "Training API")
APP_VERSION = os.getenv("APP_VERSION", "1.0.0")


# Валидация критичных настроек
def validate_config():
    """Валидация конфигурации при запуске"""
    errors = []

    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN is required")

    if not POSTGRES_HOST:
        errors.append("POSTGRES_HOST is required")

    if DB_RETRY_ATTEMPTS < 1:
        errors.append("DB_RETRY_ATTEMPTS must be >= 1")

    if DB_RETRY_DELAY < 0:
        errors.append("DB_RETRY_DELAY must be >= 0")

    if errors:
        raise ValueError(f"Configuration errors: {'; '.join(errors)}")


# Автоматическая валидация при импорте (опционально)
if os.getenv("VALIDATE_CONFIG_ON_IMPORT", "true").lower() == "true":
    try:
        validate_config()
    except ValueError as e:
        print(f"⚠️  Configuration warning: {e}")
