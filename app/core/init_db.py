import asyncio
import logging

from sqlalchemy import select, func, text
from app.core.database import async_session, DatabaseManager, db_operation, engine, Base
from app.core.exceptions import DatabaseError, ConfigurationError
from app.staff.models.roles import Role, RoleType

logger = logging.getLogger(__name__)
db_manager = DatabaseManager()


async def run_migrations():
    """Run pending database migrations (adds missing columns)"""
    migrations = [
        # Add features column to tariffs table
        {
            "name": "add_tariffs_features_column",
            "check": "SELECT column_name FROM information_schema.columns WHERE table_name='tariffs' AND column_name='features'",
            "apply": "ALTER TABLE tariffs ADD COLUMN features JSONB NOT NULL DEFAULT '[]'",
        },
        # Add excuse_note column to lesson_bookings table
        {
            "name": "add_lesson_bookings_excuse_note_column",
            "check": "SELECT column_name FROM information_schema.columns WHERE table_name='lesson_bookings' AND column_name='excuse_note'",
            "apply": "ALTER TABLE lesson_bookings ADD COLUMN excuse_note TEXT",
        },
        # Add excused_at column to lesson_bookings table
        {
            "name": "add_lesson_bookings_excused_at_column",
            "check": "SELECT column_name FROM information_schema.columns WHERE table_name='lesson_bookings' AND column_name='excused_at'",
            "apply": "ALTER TABLE lesson_bookings ADD COLUMN excused_at TIMESTAMP WITH TIME ZONE",
        },
    ]
    
    async with engine.begin() as conn:
        for migration in migrations:
            try:
                # Check if migration is needed
                result = await conn.execute(text(migration["check"]))
                exists = result.fetchone() is not None
                
                if not exists:
                    logger.info(f"Applying migration: {migration['name']}")
                    await conn.execute(text(migration["apply"]))
                    logger.info(f"✅ Migration applied: {migration['name']}")
                else:
                    logger.debug(f"Migration already applied: {migration['name']}")
            except Exception as e:
                logger.warning(f"Migration {migration['name']} skipped: {e}")


@db_operation
async def create_initial_roles():
    """Create initial roles if they don't exist"""
    async with async_session() as session:
        try:
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

        # Run pending migrations (add missing columns, etc.)
        await run_migrations()
        logger.info("✅ Database migrations checked/applied")

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
