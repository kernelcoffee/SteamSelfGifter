"""Unit tests for SettingsRepository.

Tests the singleton pattern accessor methods for the Settings model,
including automatic creation, updates, and convenience methods.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from models.settings import Settings
from repositories.settings import SettingsRepository


@pytest.fixture
async def engine():
    """
    Create an async in-memory SQLite database for testing.

    Returns:
        AsyncEngine: SQLAlchemy async engine connected to in-memory database.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    """
    Create a new async database session for each test.

    Args:
        engine: SQLAlchemy async engine fixture.

    Yields:
        AsyncSession: Database session with automatic rollback after test.
    """
    AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with AsyncSessionLocal() as session:
        yield session
        await session.rollback()


@pytest.fixture
def settings_repo(session):
    """
    Create a SettingsRepository instance.

    Args:
        session: Database session fixture.

    Returns:
        SettingsRepository: Repository instance for testing.
    """
    return SettingsRepository(session)


@pytest.mark.asyncio
async def test_get_settings_creates_if_missing(settings_repo, session):
    """Test getting settings creates record if it doesn't exist."""
    # GIVEN: An empty database with no settings
    # WHEN: Settings are retrieved
    # THEN: A new settings record should be created with default values

    settings = await settings_repo.get_settings()
    await session.commit()

    assert settings is not None
    assert settings.id == 1
    assert settings.autojoin_enabled is False  # default value
    assert settings.dlc_enabled is False  # default value


@pytest.mark.asyncio
async def test_get_settings_returns_existing(settings_repo, session):
    """Test getting settings returns existing record."""
    # GIVEN: An existing settings record
    # WHEN: Settings are retrieved
    # THEN: The existing record should be returned

    # Create settings first
    existing = await settings_repo.get_settings()
    existing.autojoin_enabled = True
    await session.commit()

    # Retrieve again
    settings = await settings_repo.get_settings()

    assert settings.id == 1
    assert settings.autojoin_enabled is True


@pytest.mark.asyncio
async def test_update_settings(settings_repo, session):
    """Test updating settings values."""
    # GIVEN: Existing settings with default values
    # WHEN: Settings are updated with new values
    # THEN: The changes should be persisted

    settings = await settings_repo.update_settings(
        autojoin_enabled=True,
        autojoin_start_at=400,
        scan_interval_minutes=45,
    )
    await session.commit()

    assert settings.autojoin_enabled is True
    assert settings.autojoin_start_at == 400
    assert settings.scan_interval_minutes == 45


@pytest.mark.asyncio
async def test_update_settings_creates_if_missing(settings_repo, session):
    """Test updating settings creates record if missing."""
    # GIVEN: An empty database
    # WHEN: Settings are updated
    # THEN: A new record should be created and updated

    settings = await settings_repo.update_settings(phpsessid="test_session")
    await session.commit()

    assert settings.id == 1
    assert settings.phpsessid == "test_session"


@pytest.mark.asyncio
async def test_get_phpsessid(settings_repo, session):
    """Test getting PHPSESSID value."""
    # GIVEN: Settings with a PHPSESSID value
    # WHEN: PHPSESSID is retrieved
    # THEN: The correct value should be returned

    await settings_repo.update_settings(phpsessid="my_session_id")
    await session.commit()

    phpsessid = await settings_repo.get_phpsessid()
    assert phpsessid == "my_session_id"


@pytest.mark.asyncio
async def test_get_phpsessid_none(settings_repo):
    """Test getting PHPSESSID when not set."""
    # GIVEN: Settings with no PHPSESSID
    # WHEN: PHPSESSID is retrieved
    # THEN: None should be returned

    phpsessid = await settings_repo.get_phpsessid()
    assert phpsessid is None


@pytest.mark.asyncio
async def test_set_phpsessid(settings_repo, session):
    """Test setting PHPSESSID value."""
    # GIVEN: Existing settings
    # WHEN: PHPSESSID is updated
    # THEN: The new value should be persisted

    settings = await settings_repo.set_phpsessid("new_session_id")
    await session.commit()

    assert settings.phpsessid == "new_session_id"

    # Verify persistence
    phpsessid = await settings_repo.get_phpsessid()
    assert phpsessid == "new_session_id"


@pytest.mark.asyncio
async def test_is_authenticated_true(settings_repo, session):
    """Test authentication check when credentials are set."""
    # GIVEN: Settings with valid PHPSESSID
    # WHEN: Authentication status is checked
    # THEN: True should be returned

    await settings_repo.set_phpsessid("valid_session")
    await session.commit()

    is_auth = await settings_repo.is_authenticated()
    assert is_auth is True


@pytest.mark.asyncio
async def test_is_authenticated_false_none(settings_repo):
    """Test authentication check when PHPSESSID is None."""
    # GIVEN: Settings with no PHPSESSID
    # WHEN: Authentication status is checked
    # THEN: False should be returned

    is_auth = await settings_repo.is_authenticated()
    assert is_auth is False


@pytest.mark.asyncio
async def test_is_authenticated_false_empty(settings_repo, session):
    """Test authentication check when PHPSESSID is empty."""
    # GIVEN: Settings with empty PHPSESSID
    # WHEN: Authentication status is checked
    # THEN: False should be returned

    await settings_repo.set_phpsessid("   ")
    await session.commit()

    is_auth = await settings_repo.is_authenticated()
    assert is_auth is False


@pytest.mark.asyncio
async def test_get_autojoin_config(settings_repo, session):
    """Test getting autojoin configuration as dictionary."""
    # GIVEN: Settings with custom autojoin values
    # WHEN: Autojoin config is retrieved
    # THEN: All autojoin fields should be in the dictionary

    await settings_repo.update_settings(
        autojoin_enabled=True,
        autojoin_start_at=400,
        autojoin_stop_at=150,
        autojoin_min_price=25,
        autojoin_min_score=8,
        autojoin_min_reviews=2000,
    )
    await session.commit()

    config = await settings_repo.get_autojoin_config()

    assert config["enabled"] is True
    assert config["start_at"] == 400
    assert config["stop_at"] == 150
    assert config["min_price"] == 25
    assert config["min_score"] == 8
    assert config["min_reviews"] == 2000


@pytest.mark.asyncio
async def test_get_autojoin_config_defaults(settings_repo):
    """Test getting autojoin config with default values."""
    # GIVEN: Settings with default values
    # WHEN: Autojoin config is retrieved
    # THEN: Default values should be in the dictionary

    config = await settings_repo.get_autojoin_config()

    assert config["enabled"] is False
    assert config["start_at"] == 350
    assert config["stop_at"] == 200
    assert config["min_price"] == 10
    assert config["min_score"] == 7
    assert config["min_reviews"] == 1000


@pytest.mark.asyncio
async def test_get_scheduler_config(settings_repo, session):
    """Test getting scheduler configuration as dictionary."""
    # GIVEN: Settings with custom scheduler values
    # WHEN: Scheduler config is retrieved
    # THEN: All scheduler fields should be in the dictionary

    await settings_repo.update_settings(
        automation_enabled=True,
        scan_interval_minutes=60,
        max_entries_per_cycle=20,
        entry_delay_min=10,
        entry_delay_max=20,
        max_scan_pages=5,
    )
    await session.commit()

    config = await settings_repo.get_scheduler_config()

    assert config["automation_enabled"] is True
    assert config["scan_interval_minutes"] == 60
    assert config["max_entries_per_cycle"] == 20
    assert config["entry_delay_min"] == 10
    assert config["entry_delay_max"] == 20
    assert config["max_scan_pages"] == 5


@pytest.mark.asyncio
async def test_get_scheduler_config_defaults(settings_repo):
    """Test getting scheduler config with default values."""
    # GIVEN: Settings with default values
    # WHEN: Scheduler config is retrieved
    # THEN: Default values should be in the dictionary

    config = await settings_repo.get_scheduler_config()

    assert config["automation_enabled"] is False
    assert config["scan_interval_minutes"] == 30
    assert config["max_entries_per_cycle"] is None
    assert config["entry_delay_min"] == 8
    assert config["entry_delay_max"] == 12
    assert config["max_scan_pages"] == 3


@pytest.mark.asyncio
async def test_multiple_updates(settings_repo, session):
    """Test multiple sequential updates to settings."""
    # GIVEN: Existing settings
    # WHEN: Multiple updates are made sequentially
    # THEN: Each update should be persisted correctly

    # First update
    await settings_repo.update_settings(autojoin_enabled=True)
    await session.commit()

    settings = await settings_repo.get_settings()
    assert settings.autojoin_enabled is True

    # Second update
    await settings_repo.update_settings(scan_interval_minutes=60)
    await session.commit()

    settings = await settings_repo.get_settings()
    assert settings.autojoin_enabled is True  # preserved
    assert settings.scan_interval_minutes == 60


@pytest.mark.asyncio
async def test_singleton_pattern_enforced(settings_repo, session):
    """Test that only one settings record exists (singleton)."""
    # GIVEN: Multiple calls to get_settings
    # WHEN: Settings are retrieved multiple times
    # THEN: The same record (id=1) should always be returned

    settings1 = await settings_repo.get_settings()
    await session.commit()

    settings2 = await settings_repo.get_settings()

    assert settings1.id == 1
    assert settings2.id == 1

    # Verify only one record exists
    from sqlalchemy import select

    result = await session.execute(select(Settings))
    all_settings = result.scalars().all()
    assert len(all_settings) == 1
