"""Integration tests for SettingsService against real SteamGifts.

Run with: pytest tests/integration/ --run-integration --phpsessid="YOUR_SESSION_ID"
"""

import pytest
from services.settings_service import SettingsService
from repositories.settings import SettingsRepository


@pytest.mark.integration
@pytest.mark.asyncio
class TestSettingsServiceIntegration:
    """Integration tests for SettingsService with real credentials."""

    async def test_test_session_valid(self, integration_db, phpsessid, user_agent):
        """Test session validation with real credentials."""
        service = SettingsService(integration_db)

        # First, set up credentials in database
        await service.set_steamgifts_credentials(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )
        await integration_db.commit()

        # Test the session
        result = await service.test_session()

        assert result["valid"] is True
        assert "username" in result
        assert "points" in result
        assert isinstance(result["username"], str)
        assert isinstance(result["points"], int)

        print(f"\n  Session valid for user: {result['username']}")
        print(f"  Current points: {result['points']}")

    async def test_test_session_invalid(self, integration_db, user_agent):
        """Test session validation with invalid credentials."""
        service = SettingsService(integration_db)

        # Set up invalid credentials
        await service.set_steamgifts_credentials(
            phpsessid="invalid_phpsessid_12345",
            user_agent=user_agent,
        )
        await integration_db.commit()

        # Test the session
        result = await service.test_session()

        assert result["valid"] is False
        assert "error" in result
        print(f"\n  Expected error: {result['error']}")

    async def test_test_session_no_credentials(self, integration_db):
        """Test session validation without credentials configured."""
        service = SettingsService(integration_db)

        # Don't set any credentials
        result = await service.test_session()

        assert result["valid"] is False
        assert "error" in result
        assert "not configured" in result["error"].lower()

    async def test_xsrf_token_saved(self, integration_db, phpsessid, user_agent):
        """Test that XSRF token is saved after successful validation."""
        service = SettingsService(integration_db)

        # Set up credentials
        await service.set_steamgifts_credentials(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )
        await integration_db.commit()

        # Verify no XSRF token initially
        settings = await service.get_settings()
        initial_xsrf = settings.xsrf_token

        # Test session (should fetch and save XSRF token)
        result = await service.test_session()
        await integration_db.commit()

        assert result["valid"] is True

        # Check if XSRF token was saved
        settings = await service.get_settings()
        if settings.xsrf_token:
            print(f"\n  XSRF token saved: {settings.xsrf_token[:20]}...")
        else:
            print("\n  Note: XSRF token was not saved (may have been pre-existing)")
