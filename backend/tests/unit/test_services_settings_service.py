"""Unit tests for SettingsService."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from models.base import Base
from services.settings_service import SettingsService


# Test database setup
@pytest.fixture
async def test_db():
    """Create in-memory test database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield async_session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.mark.asyncio
async def test_settings_service_init(test_db):
    """Test SettingsService initialization."""
    async with test_db() as session:
        service = SettingsService(session)

        assert service.session == session
        assert service.repo is not None


@pytest.mark.asyncio
async def test_get_settings(test_db):
    """Test getting settings."""
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.get_settings()

        assert settings is not None
        assert settings.id == 1


@pytest.mark.asyncio
async def test_update_settings(test_db):
    """Test updating settings."""
    async with test_db() as session:
        service = SettingsService(session)

        updated = await service.update_settings(
            autojoin_min_price=100,
            autojoin_enabled=True
        )

        assert updated.autojoin_min_price == 100
        assert updated.autojoin_enabled is True


@pytest.mark.asyncio
async def test_update_settings_validates_min_price(test_db):
    """Test validation of min_price."""
    async with test_db() as session:
        service = SettingsService(session)

        with pytest.raises(ValueError, match="autojoin_min_price must be >= 0"):
            await service.update_settings(autojoin_min_price=-10)


@pytest.mark.asyncio
async def test_update_settings_validates_min_score(test_db):
    """Test validation of min_score."""
    async with test_db() as session:
        service = SettingsService(session)

        # Too low
        with pytest.raises(ValueError, match="autojoin_min_score must be between 0 and 10"):
            await service.update_settings(autojoin_min_score=-1)

        # Too high
        with pytest.raises(ValueError, match="autojoin_min_score must be between 0 and 10"):
            await service.update_settings(autojoin_min_score=11)


@pytest.mark.asyncio
async def test_update_settings_validates_min_reviews(test_db):
    """Test validation of min_reviews."""
    async with test_db() as session:
        service = SettingsService(session)

        with pytest.raises(ValueError, match="autojoin_min_reviews must be >= 0"):
            await service.update_settings(autojoin_min_reviews=-100)


@pytest.mark.asyncio
async def test_update_settings_validates_max_scan_pages(test_db):
    """Test validation of max_scan_pages."""
    async with test_db() as session:
        service = SettingsService(session)

        with pytest.raises(ValueError, match="max_scan_pages must be >= 1"):
            await service.update_settings(max_scan_pages=0)


@pytest.mark.asyncio
async def test_update_settings_validates_max_entries(test_db):
    """Test validation of max_entries_per_cycle."""
    async with test_db() as session:
        service = SettingsService(session)

        with pytest.raises(ValueError, match="max_entries_per_cycle must be >= 1"):
            await service.update_settings(max_entries_per_cycle=0)


@pytest.mark.asyncio
async def test_update_settings_validates_entry_delays(test_db):
    """Test validation of entry delays."""
    async with test_db() as session:
        service = SettingsService(session)

        # Negative delay_min
        with pytest.raises(ValueError, match="entry_delay_min must be >= 0"):
            await service.update_settings(entry_delay_min=-5)

        # Negative delay_max
        with pytest.raises(ValueError, match="entry_delay_max must be >= 0"):
            await service.update_settings(entry_delay_max=-10)

        # delay_min > delay_max
        with pytest.raises(ValueError, match="entry_delay_min must be <= entry_delay_max"):
            await service.update_settings(entry_delay_min=20, entry_delay_max=10)


@pytest.mark.asyncio
async def test_set_steamgifts_credentials(test_db):
    """Test setting SteamGifts credentials."""
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.set_steamgifts_credentials(
            phpsessid="test_session_123",
            user_agent="Test User Agent"
        )

        assert settings.phpsessid == "test_session_123"
        assert settings.user_agent == "Test User Agent"


@pytest.mark.asyncio
async def test_set_steamgifts_credentials_strips_whitespace(test_db):
    """Test credentials are stripped of whitespace."""
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.set_steamgifts_credentials(
            phpsessid="  test_session_123  "
        )

        assert settings.phpsessid == "test_session_123"


@pytest.mark.asyncio
async def test_set_steamgifts_credentials_rejects_empty(test_db):
    """Test empty phpsessid is rejected."""
    async with test_db() as session:
        service = SettingsService(session)

        with pytest.raises(ValueError, match="phpsessid cannot be empty"):
            await service.set_steamgifts_credentials(phpsessid="")

        with pytest.raises(ValueError, match="phpsessid cannot be empty"):
            await service.set_steamgifts_credentials(phpsessid="   ")


@pytest.mark.asyncio
async def test_clear_steamgifts_credentials(test_db):
    """Test clearing SteamGifts credentials."""
    async with test_db() as session:
        service = SettingsService(session)

        # Set credentials first
        await service.set_steamgifts_credentials(
            phpsessid="test_session",
            user_agent="Test Agent"
        )

        # Clear them
        settings = await service.clear_steamgifts_credentials()

        assert settings.phpsessid is None
        # user_agent resets to default (NOT NULL field)
        assert settings.user_agent == "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:82.0) Gecko/20100101 Firefox/82.0"
        assert settings.xsrf_token is None


@pytest.mark.asyncio
async def test_is_authenticated_true(test_db):
    """Test authentication check when authenticated."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.set_steamgifts_credentials(phpsessid="test_session")

        is_auth = await service.is_authenticated()

        assert is_auth is True


@pytest.mark.asyncio
async def test_is_authenticated_false(test_db):
    """Test authentication check when not authenticated."""
    async with test_db() as session:
        service = SettingsService(session)

        is_auth = await service.is_authenticated()

        assert is_auth is False


@pytest.mark.asyncio
async def test_get_autojoin_config(test_db):
    """Test getting autojoin configuration."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.update_settings(
            autojoin_enabled=True,
            autojoin_min_price=50,
            autojoin_min_score=8
        )

        config = await service.get_autojoin_config()

        assert config["enabled"] is True
        assert config["min_price"] == 50
        assert config["min_score"] == 8


@pytest.mark.asyncio
async def test_get_scheduler_config(test_db):
    """Test getting scheduler configuration."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.update_settings(
            scan_interval_minutes=45,
            max_entries_per_cycle=15
        )

        config = await service.get_scheduler_config()

        assert config["scan_interval_minutes"] == 45
        assert config["max_entries_per_cycle"] == 15


@pytest.mark.asyncio
async def test_reset_to_defaults(test_db):
    """Test resetting to default values."""
    async with test_db() as session:
        service = SettingsService(session)

        # Set some custom values and credentials
        await service.set_steamgifts_credentials(phpsessid="test_session")
        await service.update_settings(
            autojoin_enabled=True,
            autojoin_min_price=200,
            automation_enabled=True,
            max_scan_pages=10
        )

        # Reset
        settings = await service.reset_to_defaults()

        # Credentials should be kept
        assert settings.phpsessid == "test_session"

        # Config should be reset to model defaults
        assert settings.autojoin_enabled is False
        assert settings.autojoin_start_at == 350
        assert settings.autojoin_stop_at == 200
        assert settings.autojoin_min_price == 10
        assert settings.autojoin_min_score == 7
        assert settings.autojoin_min_reviews == 1000
        assert settings.automation_enabled is False
        assert settings.max_scan_pages == 3
        assert settings.entry_delay_min == 8
        assert settings.entry_delay_max == 12


@pytest.mark.asyncio
async def test_validate_configuration_valid(test_db):
    """Test configuration validation when valid."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.set_steamgifts_credentials(phpsessid="test_session")

        result = await service.validate_configuration()

        assert result["is_valid"] is True
        assert len(result["errors"]) == 0


@pytest.mark.asyncio
async def test_validate_configuration_missing_phpsessid(test_db):
    """Test validation detects missing PHPSESSID."""
    async with test_db() as session:
        service = SettingsService(session)

        result = await service.validate_configuration()

        assert result["is_valid"] is False
        assert any("PHPSESSID" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_validate_configuration_automation_without_phpsessid(test_db):
    """Test validation detects automation enabled without PHPSESSID."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.update_settings(automation_enabled=True)

        result = await service.validate_configuration()

        assert result["is_valid"] is False
        assert any("Cannot enable automation" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_validate_configuration_invalid_delays(test_db):
    """Test validation detects invalid delay configuration."""
    async with test_db() as session:
        service = SettingsService(session)

        # Bypass update validation to create invalid state
        settings = await service.get_settings()
        settings.entry_delay_min = 20
        settings.entry_delay_max = 10
        await session.commit()

        result = await service.validate_configuration()

        assert result["is_valid"] is False
        assert any("entry_delay_min" in error and "entry_delay_max" in error
                   for error in result["errors"])


@pytest.mark.asyncio
async def test_validate_configuration_no_warnings_with_defaults(test_db):
    """Test validation with default values produces no warnings."""
    async with test_db() as session:
        service = SettingsService(session)

        await service.set_steamgifts_credentials(phpsessid="test_session")
        await service.update_settings(autojoin_enabled=True)

        result = await service.validate_configuration()

        # Should be valid with no warnings (all defaults are set)
        assert result["is_valid"] is True
        assert len(result["warnings"]) == 0
        assert len(result["errors"]) == 0
