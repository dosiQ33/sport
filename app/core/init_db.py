import asyncio
import logging
from app.core.database import async_session, engine, Base
from app.staff.models.roles import Role, RoleType

logger = logging.getLogger(__name__)


async def create_initial_roles():
    """Create initial roles if they don't exist"""
    async with async_session() as session:
        try:
            # Check if roles exist
            from sqlalchemy import select

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
                logger.info("Roles already exist, skipping creation")

        except Exception as e:
            logger.error(f"Failed to create initial roles: {e}")
            await session.rollback()
            raise


async def init_database():
    """Initialize database with tables and initial data"""
    try:
        # Create all tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created successfully")

        # Create initial data
        await create_initial_roles()

        logger.info("Database initialization completed")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(init_database())
