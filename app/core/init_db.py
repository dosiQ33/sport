import asyncio
import logging

from sqlalchemy import select, func
from app.core.database import async_session, DatabaseManager, db_operation, engine, Base
from app.core.exceptions import DatabaseError, ConfigurationError
from app.staff.models.roles import Role, RoleType

logger = logging.getLogger(__name__)
db_manager = DatabaseManager()


@db_operation
async def create_initial_roles():
    """Create initial roles if they don't exist"""
    async with async_session() as session:
        try:
            # Check if roles exist

            result = await session.execute(select(Role))
            existing_roles = result.scalars().all()

            if not existing_roles:
                logger.info("Creating initial roles...")

                roles_data = [
                    {"code": RoleType.coach, "name": "Coach"},
                    {"code": RoleType.admin, "name": "Administrator"},
                    {"code": RoleType.owner, "name": "Owner"},
                ]

                for role_data in roles_data:
                    role = Role(**role_data)
                    session.add(role)

                await session.commit()
                logger.info("Initial roles created successfully")
            else:
                logger.info(
                    f"Roles already exist ({len(existing_roles)} found), skipping creation"
                )

        except Exception as e:
            logger.error(f"Failed to create initial roles: {e}")
            await session.rollback()
            raise DatabaseError(f"Failed to create initial roles: {str(e)}")


async def init_database():
    """Initialize database with tables and initial data"""
    try:
        logger.info("Starting database initialization...")

        # Проверяем соединение с базой данных
        await db_manager.check_connection()
        logger.info("✅ Database connection verified")

        # Create all tables with retry mechanism
        await db_manager.create_tables()
        logger.info("✅ Database tables created/verified")

        # Create initial data
        await create_initial_roles()
        logger.info("✅ Initial data created/verified")

        logger.info("🎉 Database initialization completed successfully")

    except DatabaseError:
        # Наши ошибки БД - просто перебрасываем
        raise
    except Exception as e:
        logger.error(f"Unexpected error during database initialization: {e}")
        raise DatabaseError(f"Database initialization failed: {str(e)}")


async def verify_database_setup():
    """Verify that database is properly set up"""
    try:
        logger.info("Verifying database setup...")

        async with async_session() as session:
            # Проверяем наличие ролей

            roles_count = await session.execute(select(func.count(Role.id)))
            count = roles_count.scalar()

            expected_roles = len(RoleType)
            if count != expected_roles:
                raise DatabaseError(f"Expected {expected_roles} roles, found {count}")

            logger.info(f"✅ Database verification passed: {count} roles found")
            return True

    except Exception as e:
        logger.error(f"Database verification failed: {e}")
        raise DatabaseError(f"Database verification failed: {str(e)}")


async def reset_database():
    """Reset database (for development/testing only)"""
    import os

    environment = os.getenv("ENVIRONMENT", "production").lower()
    if environment not in ["development", "dev", "test"]:
        raise ConfigurationError(
            "ENVIRONMENT",
            "Database reset is only allowed in development or test environments",
        )

    try:
        logger.warning("🚨 RESETTING DATABASE - ALL DATA WILL BE LOST!")

        # Drop all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

        logger.info("✅ All tables dropped")

        # Recreate everything
        await init_database()

        logger.info("✅ Database reset completed")

    except Exception as e:
        logger.error(f"Database reset failed: {e}")
        raise DatabaseError(f"Database reset failed: {str(e)}")


if __name__ == "__main__":
    import sys

    async def main():
        if len(sys.argv) > 1:
            command = sys.argv[1]

            if command == "init":
                await init_database()
            elif command == "verify":
                await verify_database_setup()
            elif command == "reset":
                await reset_database()
            else:
                print(f"Unknown command: {command}")
                print("Available commands: init, verify, reset")
                sys.exit(1)
        else:
            await init_database()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Database initialization cancelled by user")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        sys.exit(1)
