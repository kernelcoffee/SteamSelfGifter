"""Database session management for async SQLAlchemy with SQLite."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)

from core.config import settings

# Create async engine for SQLite
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite-specific settings
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    # Connection pool settings (not used by SQLite, but good practice)
    pool_pre_ping=True,
)

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function for FastAPI to get database sessions.

    Auto-commits on successful request completion, rolls back on error.

    Yields:
        AsyncSession: Database session that will be automatically closed after use.

    Example:
        @app.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(Item))
            return result.scalars().all()
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """
    Initialize the database by running Alembic migrations.

    This ensures the database schema is always up to date with the models.
    Uses Alembic's upgrade command to apply any pending migrations.

    For existing databases without alembic_version table, it will first
    stamp the database at the initial migration to avoid recreating tables.
    """
    import os
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from alembic import command
    from alembic.config import Config
    import sqlite3

    def run_migrations():
        # Get the directory where alembic.ini is located
        src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alembic_ini = os.path.join(src_dir, "alembic.ini")

        # Create Alembic config
        alembic_cfg = Config(alembic_ini)

        # Set the script location relative to alembic.ini
        alembic_cfg.set_main_option("script_location", os.path.join(src_dir, "alembic"))

        # Check if this is an existing database that needs to be stamped
        # Extract database path from the URL
        db_url = settings.database_url
        if "sqlite" in db_url:
            # Parse sqlite URL to get file path
            db_path = db_url.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")

            if os.path.exists(db_path):
                # Check if alembic_version table exists and has entries
                conn = sqlite3.connect(db_path)
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"
                )
                has_alembic_table = cursor.fetchone() is not None

                # Check if alembic_version has any entries
                alembic_has_entries = False
                if has_alembic_table:
                    cursor = conn.execute("SELECT COUNT(*) FROM alembic_version")
                    alembic_has_entries = cursor.fetchone()[0] > 0

                # Check if settings table exists (means existing database)
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='settings'"
                )
                has_tables = cursor.fetchone() is not None
                conn.close()

                if has_tables and not alembic_has_entries:
                    # Existing database without alembic tracking (or empty alembic_version) - stamp it
                    command.stamp(alembic_cfg, "head")
                    return  # No upgrade needed, already at head

        # Run migrations
        command.upgrade(alembic_cfg, "head")

    # Run migrations in a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        await loop.run_in_executor(executor, run_migrations)


async def close_db() -> None:
    """Close database connections and dispose of the engine."""
    await engine.dispose()
