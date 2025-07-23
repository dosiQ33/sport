import logging
import time
from typing import Any, Dict
import json

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO", log_format: str = "text"):
    """
    Настройка системы логирования

    Args:
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_format: Формат логов (text, json)
    """

    # Создаем форматтер
    if log_format.lower() == "json":
        formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

    # Настраиваем root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper()))

    # Удаляем существующие handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Добавляем console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # Настраиваем уровни для специфичных логгеров
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    logger.info(f"Logging configured: level={log_level}, format={log_format}")


class JsonFormatter(logging.Formatter):
    """JSON форматтер для структурированного логирования"""

    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Добавляем дополнительные поля из extra
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in [
                    "name",
                    "msg",
                    "args",
                    "levelname",
                    "levelno",
                    "pathname",
                    "filename",
                    "module",
                    "exc_info",
                    "exc_text",
                    "stack_info",
                    "lineno",
                    "funcName",
                    "created",
                    "msecs",
                    "relativeCreated",
                    "thread",
                    "threadName",
                    "processName",
                    "process",
                    "getMessage",
                ]:
                    try:
                        # Пытаемся сериализовать значение
                        json.dumps(value)
                        log_entry[key] = value
                    except (TypeError, ValueError):
                        log_entry[key] = str(value)

        # Добавляем exception info если есть
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


class ErrorTracker:
    """Класс для отслеживания ошибок и их статистики"""

    def __init__(self):
        self.error_counts = {}
        self.last_errors = []
        self.max_history = 100

    def track_error(
        self, error_type: str, error_message: str, context: Dict[str, Any] = None
    ):
        """Отследить ошибку"""
        # Увеличиваем счетчик
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

        # Добавляем в историю
        error_entry = {
            "timestamp": time.time(),
            "type": error_type,
            "message": error_message,
            "context": context or {},
        }

        self.last_errors.append(error_entry)

        # Ограничиваем размер истории
        if len(self.last_errors) > self.max_history:
            self.last_errors = self.last_errors[-self.max_history :]

        logger.warning(
            f"Error tracked: {error_type}",
            extra={
                "error_type": error_type,
                "error_message": error_message,
                "total_count": self.error_counts[error_type],
                "context": context,
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        """Получить статистику ошибок"""
        return {
            "error_counts": self.error_counts.copy(),
            "total_errors": sum(self.error_counts.values()),
            "unique_error_types": len(self.error_counts),
            "last_errors": self.last_errors[-10:],  # Последние 10 ошибок
        }

    def reset_stats(self):
        """Сбросить статистику"""
        self.error_counts.clear()
        self.last_errors.clear()
        logger.info("Error tracking stats reset")


# Глобальный трекер ошибок
error_tracker = ErrorTracker()


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер с настроенным именем

    Args:
        name: Имя логгера

    Returns:
        Настроенный логгер
    """
    return logging.getLogger(name)


def log_business_event(
    event: str, entity_type: str, entity_id: int, details: Dict[str, Any] = None
):
    """
    Логировать бизнес-событие

    Args:
        event: Название события
        entity_type: Тип сущности (club, section, user)
        entity_id: ID сущности
        details: Дополнительные детали
    """
    logger.info(
        f"Business event: {event}",
        extra={
            "event": event,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "details": details or {},
            "category": "business_event",
        },
    )
