import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, Any, AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.sql import text
from sqlalchemy.exc import (
    SQLAlchemyError,
    OperationalError,
    DisconnectionError,
    TimeoutError,
)
from asyncpg.exceptions import (
    ConnectionFailureError,
    ConnectionDoesNotExistError,
)

from .config import DATABASE_URL, DB_RETRY_ATTEMPTS, DB_RETRY_DELAY
from .exceptions import DatabaseConnectionError, DatabaseTimeoutError

logger = logging.getLogger(__name__)

# Настройки engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,  # Отключаем echo в production
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=3600,  # Переподключение каждый час
    pool_pre_ping=True,  # Проверка соединения перед использованием
)

async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,  # Отключаем автофлаш для лучшего контроля
)

Base = declarative_base()

# Типы для retry decorator
F = TypeVar("F", bound=Callable[..., Any])


def db_retry(
    max_attempts: int = None,
    delay: float = None,
    backoff_factor: float = 2.0,
    exceptions: tuple = None,
) -> Callable[[F], F]:
    """
    Decorator для повторных попыток операций с базой данных

    Args:
        max_attempts: Максимальное количество попыток (по умолчанию из config)
        delay: Начальная задержка между попытками (по умолчанию из config)
        backoff_factor: Множитель для увеличения задержки
        exceptions: Кортеж исключений для повтора
    """
    if max_attempts is None:
        max_attempts = DB_RETRY_ATTEMPTS

    if delay is None:
        delay = DB_RETRY_DELAY

    if exceptions is None:
        exceptions = (
            OperationalError,
            DisconnectionError,
            TimeoutError,
            ConnectionFailureError,
            ConnectionDoesNotExistError,
        )

    def decorator(func: F) -> F:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            current_delay = delay
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_attempts - 1:
                        # Последняя попытка - выбрасываем исключение
                        break

                    # Логируем попытку
                    logger.warning(
                        f"Database operation failed (attempt {attempt + 1}/{max_attempts}): {str(e)}",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_attempts,
                            "exception_type": type(e).__name__,
                        },
                    )

                    # Ждем перед следующей попыткой
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor

                except Exception as e:
                    # Для других исключений не делаем retry
                    logger.error(
                        f"Non-retryable database error in {func.__name__}: {str(e)}",
                        extra={
                            "function": func.__name__,
                            "exception_type": type(e).__name__,
                        },
                    )
                    raise

            # Если мы здесь, значит все попытки исчерпаны
            logger.error(
                f"Database operation failed after {max_attempts} attempts: {str(last_exception)}",
                extra={
                    "function": func.__name__,
                    "max_attempts": max_attempts,
                    "final_exception": str(last_exception),
                },
            )

            # Преобразуем в наше исключение
            if isinstance(
                last_exception,
                (
                    ConnectionFailureError,
                    ConnectionDoesNotExistError,
                    DisconnectionError,
                ),
            ):
                raise DatabaseConnectionError(
                    f"Database connection failed after {max_attempts} attempts"
                )
            elif isinstance(last_exception, TimeoutError):
                raise DatabaseTimeoutError(func.__name__, 30)
            else:
                raise last_exception

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Для синхронных функций просто вызываем без retry
            return func(*args, **kwargs)

        # Возвращаем соответствующий wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии базы данных с retry механизмом
    """
    session = None
    max_attempts = DB_RETRY_ATTEMPTS
    current_delay = DB_RETRY_DELAY

    # Retry только для создания сессии
    for attempt in range(max_attempts):
        try:
            session = async_session()
            break
        except (
            OperationalError,
            DisconnectionError,
            ConnectionFailureError,
            ConnectionDoesNotExistError,
        ) as e:
            if attempt == max_attempts - 1:
                logger.error(
                    f"Failed to create session after {max_attempts} attempts: {str(e)}"
                )
                raise DatabaseConnectionError(
                    f"Database connection failed after {max_attempts} attempts"
                )

            logger.warning(
                f"Session creation failed (attempt {attempt + 1}/{max_attempts}): {str(e)}"
            )
            await asyncio.sleep(current_delay)
            current_delay *= 2.0

    if session is None:
        raise DatabaseConnectionError("Failed to create database session")

    try:
        yield session
    except Exception as e:
        await session.rollback()
        logger.error(f"Session error: {str(e)}")
        raise
    finally:
        await session.close()


class DatabaseManager:
    """Менеджер для управления операциями с базой данных"""

    @staticmethod
    @db_retry()
    async def execute_with_retry(
        session: AsyncSession, operation: Callable, *args, **kwargs
    ):
        """
        Выполнить операцию с базой данных с retry механизмом

        Args:
            session: Сессия базы данных
            operation: Функция для выполнения
            *args, **kwargs: Аргументы для функции
        """
        try:
            result = await operation(session, *args, **kwargs)
            await session.commit()
            return result
        except Exception as e:
            await session.rollback()
            logger.error(f"Database operation failed: {str(e)}")
            raise

    @staticmethod
    @db_retry()
    async def create_tables():
        """Создание всех таблиц в базе данных"""
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {str(e)}")
            raise

    @staticmethod
    @db_retry()
    async def check_connection():
        """Проверка соединения с базой данных"""
        try:
            async with engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info("Database connection check successful")
            return True
        except Exception as e:
            logger.error(f"Database connection check failed: {str(e)}")
            raise DatabaseConnectionError("Database connection check failed")

    @staticmethod
    async def close_connections():
        """Закрытие всех соединений с базой данных"""
        try:
            await engine.dispose()
            logger.info("Database connections closed successfully")
        except Exception as e:
            logger.error(f"Error closing database connections: {str(e)}")


# Экспортируем для обратной совместимости
db_manager = DatabaseManager()


class TransactionManager:
    """Менеджер транзакций с автоматическим retry"""

    def __init__(self, session: AsyncSession):
        self.session = session

    @db_retry()
    async def execute(self, operation: Callable, *args, **kwargs):
        """
        Выполнить операцию в транзакции
        """
        try:
            result = await operation(self.session, *args, **kwargs)
            await self.session.commit()
            return result
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Transaction failed: {str(e)}")
            raise

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()


# Хелпер функции для использования в CRUD
async def with_db_transaction(
    session: AsyncSession, operation: Callable, *args, **kwargs
):
    """
    Хелпер для выполнения операции в транзакции с retry
    """
    transaction_manager = TransactionManager(session)
    return await transaction_manager.execute(operation, *args, **kwargs)


# Декораторы для CRUD операций
def db_operation(func: F) -> F:
    """
    Декоратор для CRUD операций с автоматическим retry и логированием
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        operation_name = func.__name__

        try:
            logger.debug(f"Starting database operation: {operation_name}")
            result = await func(*args, **kwargs)
            logger.debug(f"Database operation completed: {operation_name}")
            return result

        except SQLAlchemyError as e:
            logger.error(
                f"SQLAlchemy error in {operation_name}: {str(e)}",
                extra={"operation": operation_name, "exception_type": type(e).__name__},
            )
            raise

        except Exception as e:
            logger.error(
                f"Unexpected error in {operation_name}: {str(e)}",
                extra={"operation": operation_name, "exception_type": type(e).__name__},
            )
            raise

    return wrapper
