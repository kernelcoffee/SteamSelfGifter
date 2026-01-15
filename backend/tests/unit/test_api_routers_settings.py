"""Unit tests for settings API router."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from pydantic import ValidationError

from api.routers.settings import (
    get_settings,
    update_settings,
    set_credentials,
    clear_credentials,
    validate_configuration,
    reset_to_defaults,
)
from api.schemas.settings import SettingsUpdate, SteamGiftsCredentials
from models.settings import Settings


# Mock settings data
def create_mock_settings():
    """Create a mock Settings object."""
    settings = MagicMock(spec=Settings)
    settings.id = 1
    settings.phpsessid = "test_session"
    settings.user_agent = "Mozilla/5.0"
    settings.xsrf_token = None
    settings.dlc_enabled = False
    settings.autojoin_enabled = True
    settings.autojoin_start_at = 350
    settings.autojoin_stop_at = 200
    settings.autojoin_min_price = 10
    settings.autojoin_min_score = 7
    settings.autojoin_min_reviews = 1000
    settings.scan_interval_minutes = 30
    settings.max_entries_per_cycle = 10
    settings.automation_enabled = True
    settings.max_scan_pages = 3
    settings.entry_delay_min = 8
    settings.entry_delay_max = 12
    settings.last_synced_at = None
    settings.created_at = datetime.utcnow()
    settings.updated_at = datetime.utcnow()
    return settings


@pytest.mark.asyncio
async def test_get_settings():
    """Test GET /settings endpoint."""
    mock_service = AsyncMock()
    mock_settings = create_mock_settings()
    mock_service.get_settings.return_value = mock_settings

    result = await get_settings(mock_service)

    assert result["success"] is True
    assert "data" in result
    assert result["data"]["id"] == 1
    assert result["data"]["phpsessid"] == "test_session"
    mock_service.get_settings.assert_called_once()


@pytest.mark.asyncio
async def test_update_settings():
    """Test PUT /settings endpoint."""
    mock_service = AsyncMock()
    mock_settings = create_mock_settings()
    mock_service.update_settings.return_value = mock_settings

    update_data = SettingsUpdate(
        autojoin_enabled=True,
        autojoin_min_price=50
    )

    result = await update_settings(update_data, mock_service)

    assert result["success"] is True
    assert "data" in result
    mock_service.update_settings.assert_called_once()


@pytest.mark.asyncio
async def test_update_settings_no_fields():
    """Test PUT /settings with no fields raises error."""
    mock_service = AsyncMock()

    update_data = SettingsUpdate()  # No fields

    with pytest.raises(HTTPException) as exc_info:
        await update_settings(update_data, mock_service)

    assert exc_info.value.status_code == 400
    assert "No fields provided" in exc_info.value.detail


@pytest.mark.asyncio
async def test_update_settings_validation_error():
    """Test PUT /settings with validation error from service."""
    mock_service = AsyncMock()
    mock_service.update_settings.side_effect = ValueError("Invalid value")

    # Use valid Pydantic values that will pass schema validation
    # but trigger service validation error
    update_data = SettingsUpdate(autojoin_min_price=50)

    with pytest.raises(HTTPException) as exc_info:
        await update_settings(update_data, mock_service)

    assert exc_info.value.status_code == 400
    assert "Invalid value" in exc_info.value.detail


@pytest.mark.asyncio
async def test_set_credentials():
    """Test POST /settings/credentials endpoint."""
    mock_service = AsyncMock()
    mock_settings = create_mock_settings()
    mock_service.set_steamgifts_credentials.return_value = mock_settings

    credentials = SteamGiftsCredentials(
        phpsessid="new_session",
        user_agent="Custom Agent"
    )

    result = await set_credentials(credentials, mock_service)

    assert result["success"] is True
    assert "data" in result
    mock_service.set_steamgifts_credentials.assert_called_once_with(
        phpsessid="new_session",
        user_agent="Custom Agent"
    )


@pytest.mark.asyncio
async def test_set_credentials_validation_error():
    """Test POST /settings/credentials with validation error."""
    mock_service = AsyncMock()
    mock_service.set_steamgifts_credentials.side_effect = ValueError("Invalid credentials")

    credentials = SteamGiftsCredentials(phpsessid="test")

    with pytest.raises(HTTPException) as exc_info:
        await set_credentials(credentials, mock_service)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_clear_credentials():
    """Test DELETE /settings/credentials endpoint."""
    mock_service = AsyncMock()

    result = await clear_credentials(mock_service)

    assert result["success"] is True
    assert result["data"]["message"] == "Credentials cleared successfully"
    mock_service.clear_steamgifts_credentials.assert_called_once()


@pytest.mark.asyncio
async def test_validate_configuration():
    """Test POST /settings/validate endpoint."""
    mock_service = AsyncMock()
    mock_service.validate_configuration.return_value = {
        "is_valid": True,
        "errors": [],
        "warnings": []
    }

    result = await validate_configuration(mock_service)

    assert result["success"] is True
    assert result["data"]["is_valid"] is True
    assert result["data"]["errors"] == []
    mock_service.validate_configuration.assert_called_once()


@pytest.mark.asyncio
async def test_validate_configuration_with_errors():
    """Test POST /settings/validate with errors."""
    mock_service = AsyncMock()
    mock_service.validate_configuration.return_value = {
        "is_valid": False,
        "errors": ["PHPSESSID not configured"],
        "warnings": ["Consider setting minimum price"]
    }

    result = await validate_configuration(mock_service)

    assert result["success"] is True
    assert result["data"]["is_valid"] is False
    assert len(result["data"]["errors"]) == 1
    assert len(result["data"]["warnings"]) == 1


@pytest.mark.asyncio
async def test_reset_to_defaults():
    """Test POST /settings/reset endpoint."""
    mock_service = AsyncMock()
    mock_settings = create_mock_settings()
    mock_service.reset_to_defaults.return_value = mock_settings

    result = await reset_to_defaults(mock_service)

    assert result["success"] is True
    assert "data" in result
    mock_service.reset_to_defaults.assert_called_once()


