"""End-to-end tests for settings API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_settings_creates_default(test_client: AsyncClient):
    """Test GET /api/v1/settings creates default settings if none exist."""
    response = await test_client.get("/api/v1/settings")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data

    settings = data["data"]
    assert settings["id"] == 1
    assert settings["phpsessid"] is None
    # Check actual defaults from model
    assert settings["automation_enabled"] is False
    assert settings["autojoin_enabled"] is False  # Default is False
    assert settings["autojoin_min_price"] == 10  # Default is 10
    assert settings["autojoin_min_score"] == 7  # Default is 7


@pytest.mark.asyncio
async def test_get_settings_returns_existing(test_client: AsyncClient):
    """Test GET /api/v1/settings returns existing settings on subsequent calls."""
    # First call creates settings
    response1 = await test_client.get("/api/v1/settings")
    assert response1.status_code == 200

    # Second call returns same settings
    response2 = await test_client.get("/api/v1/settings")
    assert response2.status_code == 200

    data1 = response1.json()["data"]
    data2 = response2.json()["data"]
    assert data1["id"] == data2["id"]


@pytest.mark.asyncio
async def test_update_settings(test_client: AsyncClient):
    """Test PUT /api/v1/settings updates settings."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Update settings with valid values
    update_data = {
        "autojoin_enabled": True,
        "autojoin_min_price": 100,
        "autojoin_min_score": 8,
    }
    response = await test_client.put("/api/v1/settings", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["autojoin_enabled"] is True
    assert data["data"]["autojoin_min_price"] == 100
    assert data["data"]["autojoin_min_score"] == 8


@pytest.mark.asyncio
async def test_update_settings_partial(test_client: AsyncClient):
    """Test PUT /api/v1/settings allows partial updates."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Update only one field
    update_data = {"autojoin_min_price": 50}
    response = await test_client.put("/api/v1/settings", json=update_data)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["autojoin_min_price"] == 50
    # Other fields should remain at defaults
    assert data["data"]["autojoin_min_score"] == 7


@pytest.mark.asyncio
async def test_update_settings_validation_error(test_client: AsyncClient):
    """Test PUT /api/v1/settings validates input."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Try to update with invalid values (score > 10)
    update_data = {
        "autojoin_min_score": 15,  # Max is 10
    }
    response = await test_client.put("/api/v1/settings", json=update_data)

    # 422 Unprocessable Entity for Pydantic schema validation errors
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_settings_empty_body(test_client: AsyncClient):
    """Test PUT /api/v1/settings rejects empty updates."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Try to update with empty body
    response = await test_client.put("/api/v1/settings", json={})

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_set_credentials(test_client: AsyncClient):
    """Test POST /api/v1/settings/credentials sets credentials."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Set credentials
    credentials = {
        "phpsessid": "test_session_id_123",
        "user_agent": "Mozilla/5.0 Test Agent",
    }
    response = await test_client.post("/api/v1/settings/credentials", json=credentials)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["phpsessid"] == "test_session_id_123"
    assert data["data"]["user_agent"] == "Mozilla/5.0 Test Agent"


@pytest.mark.asyncio
async def test_set_credentials_phpsessid_only(test_client: AsyncClient):
    """Test POST /api/v1/settings/credentials with only PHPSESSID."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Set only phpsessid
    credentials = {
        "phpsessid": "session_only_123",
    }
    response = await test_client.post("/api/v1/settings/credentials", json=credentials)

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["phpsessid"] == "session_only_123"


@pytest.mark.asyncio
async def test_set_credentials_empty_phpsessid(test_client: AsyncClient):
    """Test POST /api/v1/settings/credentials rejects empty PHPSESSID."""
    # First create settings
    await test_client.get("/api/v1/settings")

    # Set empty credentials
    credentials = {
        "phpsessid": "   ",  # Only whitespace
    }
    response = await test_client.post("/api/v1/settings/credentials", json=credentials)

    # 422 Unprocessable Entity for Pydantic validator rejection
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_clear_credentials(test_client: AsyncClient):
    """Test DELETE /api/v1/settings/credentials clears credentials."""
    # First set credentials
    await test_client.get("/api/v1/settings")
    await test_client.post(
        "/api/v1/settings/credentials",
        json={"phpsessid": "test_session"},
    )

    # Clear credentials
    response = await test_client.delete("/api/v1/settings/credentials")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "message" in data["data"]

    # Verify credentials are cleared
    get_response = await test_client.get("/api/v1/settings")
    settings = get_response.json()["data"]
    assert settings["phpsessid"] is None


@pytest.mark.asyncio
async def test_validate_configuration_not_authenticated(test_client: AsyncClient):
    """Test POST /api/v1/settings/validate with no credentials."""
    # Create default settings (no credentials)
    await test_client.get("/api/v1/settings")

    response = await test_client.post("/api/v1/settings/validate")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Should have errors because not authenticated
    assert data["data"]["is_valid"] is False
    assert len(data["data"]["errors"]) > 0


@pytest.mark.asyncio
async def test_validate_configuration_authenticated(test_client: AsyncClient):
    """Test POST /api/v1/settings/validate with credentials."""
    # Set up credentials
    await test_client.get("/api/v1/settings")
    await test_client.post(
        "/api/v1/settings/credentials",
        json={"phpsessid": "valid_session"},
    )

    response = await test_client.post("/api/v1/settings/validate")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["is_valid"] is True


@pytest.mark.asyncio
async def test_reset_settings(test_client: AsyncClient):
    """Test POST /api/v1/settings/reset resets to defaults."""
    # Set up custom settings
    await test_client.get("/api/v1/settings")
    await test_client.put(
        "/api/v1/settings",
        json={
            "autojoin_min_price": 200,
            "autojoin_min_score": 9,
        },
    )
    await test_client.post(
        "/api/v1/settings/credentials",
        json={"phpsessid": "keep_this"},
    )

    # Reset settings
    response = await test_client.post("/api/v1/settings/reset")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Credentials should be preserved
    assert data["data"]["phpsessid"] == "keep_this"
    # Other settings should be reset to defaults
    assert data["data"]["autojoin_min_price"] == 10  # Model default
    assert data["data"]["autojoin_min_score"] == 7  # Model default


@pytest.mark.asyncio
async def test_update_automation_enabled(test_client: AsyncClient):
    """Test updating automation_enabled via PUT."""
    await test_client.get("/api/v1/settings")

    # Enable automation
    response = await test_client.put(
        "/api/v1/settings",
        json={"automation_enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["data"]["automation_enabled"] is True

    # Disable automation
    response = await test_client.put(
        "/api/v1/settings",
        json={"automation_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["data"]["automation_enabled"] is False


@pytest.mark.asyncio
async def test_update_autojoin_enabled(test_client: AsyncClient):
    """Test updating autojoin_enabled via PUT."""
    await test_client.get("/api/v1/settings")

    # Enable autojoin
    response = await test_client.put(
        "/api/v1/settings",
        json={"autojoin_enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["data"]["autojoin_enabled"] is True

    # Disable autojoin
    response = await test_client.put(
        "/api/v1/settings",
        json={"autojoin_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["data"]["autojoin_enabled"] is False


@pytest.mark.asyncio
async def test_update_multiple_settings(test_client: AsyncClient):
    """Test updating multiple settings at once."""
    await test_client.get("/api/v1/settings")

    update_data = {
        "autojoin_enabled": True,
        "autojoin_min_price": 50,
        "autojoin_min_score": 8,
        "autojoin_min_reviews": 500,
        "max_scan_pages": 5,
    }
    response = await test_client.put("/api/v1/settings", json=update_data)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["autojoin_enabled"] is True
    assert data["autojoin_min_price"] == 50
    assert data["autojoin_min_score"] == 8
    assert data["autojoin_min_reviews"] == 500
    assert data["max_scan_pages"] == 5
