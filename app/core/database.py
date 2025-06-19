import logging
from functools import wraps
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    after_log,
    before_sleep_log,
)

from .config import DATABASE_URL
from .exceptions import DatabaseError

logger = logging.getLogger(__name__)

engine = create_async_engine(
    DATABASE_URL, echo=True, pool_size=20, max_overflow=0, pool_timeout=30
)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()


async def get_session():
    async with async_session() as session:
        yield session


def database_operation(func):
    """
    Decorator for database operations that provides consistent error handling
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except IntegrityError as e:
            logger.error(f"Integrity error in {func.__name__}: {e}")
            # Extract meaningful error message
            if "unique constraint" in str(e).lower():
                raise DatabaseError(
                    "Resource already exists",
                    error_code="DUPLICATE_RESOURCE",
                    details={"constraint": "unique_constraint"},
                )
            elif "foreign key constraint" in str(e).lower():
                raise DatabaseError(
                    "Referenced resource not found",
                    error_code="INVALID_REFERENCE",
                    details={"constraint": "foreign_key"},
                )
            else:
                raise DatabaseError(
                    "Data integrity violation", error_code="INTEGRITY_ERROR"
                )
        except OperationalError as e:
            logger.error(f"Operational error in {func.__name__}: {e}")
            raise DatabaseError(
                "Database connection error",
                error_code="CONNECTION_ERROR",
                details={"operation": func.__name__},
            )
        except SQLAlchemyError as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise DatabaseError(
                "Database operation failed",
                error_code="DATABASE_ERROR",
                details={"operation": func.__name__},
            )
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise

    return wrapper


def retry_db_operation(
    max_attempts: int = 3, min_wait: float = 1.0, max_wait: float = 10.0
):
    """
    Decorator for database operations that should be retried on failure
    """

    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
            retry=retry_if_exception_type((OperationalError, OSError)),
            after=after_log(logger, logging.WARNING),
            before_sleep=before_sleep_log(logger, logging.INFO),
        )
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


# Helper function for transaction management
async def execute_in_transaction(session: AsyncSession, operations: list):
    """
    Execute multiple database operations in a single transaction

    Args:
        session: Database session
        operations: List of async functions to execute

    Returns:
        List of results from operations
    """
    try:
        results = []
        for operation in operations:
            result = await operation()
            results.append(result)

        await session.commit()
        return results
    except Exception as e:
        await session.rollback()
        logger.error(f"Transaction failed: {e}")
        raise


# Connection health check
async def check_database_health() -> bool:
    """
    Check if database connection is healthy

    Returns:
        bool: True if database is accessible, False otherwise
    """
    try:
        async with async_session() as session:
            await session.execute("SELECT 1")
            return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
