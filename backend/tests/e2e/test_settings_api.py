"""End-to-end tests for settings API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.settings import SettingsRepository


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
    assert settings["autojoin_min_reviews"] == 1000
    assert settings["max_entries_per_cycle"] == 10
    assert settings["autojoin_priorities"] == [{"type": "wishlist"}]
    assert settings["excluded_genres"] == []
    assert settings["included_genres"] == []
    for removed in ("wishlist_priority_enabled", "dlc_priority_enabled",
                    "ending_soon_priority_enabled", "ending_soon_threshold_minutes"):
        assert removed not in settings


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


async def _settings(test_client: AsyncClient) -> dict:
    return (await test_client.get("/api/v1/settings")).json()["data"]


@pytest.mark.asyncio
async def test_update_priority_list_round_trips_in_order(test_client: AsyncClient):
    priorities = [{"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 120}, {"type": "wishlist"}]

    response = await test_client.put("/api/v1/settings", json={"autojoin_priorities": priorities})

    assert response.status_code == 200
    assert response.json()["data"]["autojoin_priorities"] == priorities
    assert (await _settings(test_client))["autojoin_priorities"] == priorities


@pytest.mark.asyncio
async def test_update_priority_list_empty(test_client: AsyncClient):
    response = await test_client.put("/api/v1/settings", json={"autojoin_priorities": []})

    assert response.status_code == 200
    assert (await _settings(test_client))["autojoin_priorities"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [5, 10080])
async def test_update_priority_threshold_bounds_accepted(test_client: AsyncClient, value):
    item = {"type": "ending_soon", "threshold_minutes": value}

    response = await test_client.put("/api/v1/settings", json={"autojoin_priorities": [item]})

    assert response.status_code == 200
    assert (await _settings(test_client))["autojoin_priorities"] == [item]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [
    [{"type": "bogus"}],
    [{"type": "wishlist"}, {"type": "wishlist"}],
    [{"type": "ending_soon"}],
    [{"type": "ending_soon", "threshold_minutes": 4}],
    [{"type": "ending_soon", "threshold_minutes": 10081}],
    [{"type": "ending_soon", "threshold_minutes": "abc"}],
    [{"type": "wishlist", "threshold_minutes": 10}],
    "wishlist",
    [{"type": "wishlist"}, {"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 60}, {"type": "dlc"}],
])
async def test_update_bad_priority_list_is_422_and_writes_nothing(test_client: AsyncClient, value):
    await test_client.put("/api/v1/settings", json={"autojoin_priorities": [{"type": "dlc"}]})

    response = await test_client.put(
        "/api/v1/settings", json={"autojoin_priorities": value, "autojoin_min_price": 99}
    )

    assert response.status_code == 422
    settings = await _settings(test_client)
    assert settings["autojoin_priorities"] == [{"type": "dlc"}]
    assert settings["autojoin_min_price"] == 10


@pytest.mark.asyncio
async def test_update_null_priority_list_means_unchanged(test_client: AsyncClient):
    await test_client.put("/api/v1/settings", json={"autojoin_priorities": [{"type": "dlc"}]})

    response = await test_client.put("/api/v1/settings", json={"autojoin_priorities": None})
    assert response.status_code == 400
    assert response.json()["detail"] == "No fields provided for update"

    response = await test_client.put(
        "/api/v1/settings", json={"autojoin_priorities": None, "autojoin_enabled": True}
    )
    assert response.status_code == 200
    assert response.json()["data"]["autojoin_priorities"] == [{"type": "dlc"}]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["autojoin_min_score", "autojoin_min_reviews", "autojoin_max_game_age"])
async def test_update_explicit_null_turns_a_filter_off(test_client: AsyncClient, field):
    await test_client.put("/api/v1/settings", json={field: 3})

    response = await test_client.put("/api/v1/settings", json={field: None})

    assert response.status_code == 200
    assert (await _settings(test_client))[field] is None


@pytest.mark.asyncio
async def test_update_omitted_threshold_is_unchanged_and_zero_is_stored(test_client: AsyncClient):
    await test_client.put("/api/v1/settings", json={"autojoin_min_score": None})

    await test_client.put("/api/v1/settings", json={"autojoin_enabled": True})
    assert (await _settings(test_client))["autojoin_min_score"] is None

    response = await test_client.put("/api/v1/settings", json={"autojoin_min_score": 0})
    assert response.status_code == 200
    assert (await _settings(test_client))["autojoin_min_score"] == 0

    response = await test_client.put("/api/v1/settings", json={"autojoin_min_score": 11})
    assert response.status_code == 422
    assert (await _settings(test_client))["autojoin_min_score"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "excluded_genres", "included_genres", "user_agent", "max_entries_per_cycle", "autojoin_start_at",
])
async def test_update_null_for_a_not_null_field_is_400(test_client: AsyncClient, field):
    before = await _settings(test_client)

    response = await test_client.put("/api/v1/settings", json={field: None, "autojoin_min_price": 99})

    assert response.status_code == 400
    assert response.json()["detail"] == f"{field} cannot be null"
    after = await _settings(test_client)
    assert after[field] == before[field]
    assert after["autojoin_min_price"] == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [0, -1])
async def test_update_cap_below_one_is_422(test_client: AsyncClient, value):
    response = await test_client.put("/api/v1/settings", json={"max_entries_per_cycle": value})

    assert response.status_code == 422
    assert (await _settings(test_client))["max_entries_per_cycle"] == 10


@pytest.mark.asyncio
async def test_removed_flag_fields_are_ignored(test_client: AsyncClient):
    response = await test_client.put(
        "/api/v1/settings", json={"wishlist_priority_enabled": False, "autojoin_min_price": 20}
    )

    assert response.status_code == 200
    assert "wishlist_priority_enabled" not in response.json()["data"]
    assert response.json()["data"]["autojoin_priorities"] == [{"type": "wishlist"}]


@pytest.mark.asyncio
async def test_update_excluded_genres_normalizes_and_round_trips(test_client: AsyncClient):
    """Items are stripped, empties dropped, case-insensitive duplicates removed
    keeping the first spelling; the response and a re-read echo the result."""
    response = await test_client.put(
        "/api/v1/settings", json={"excluded_genres": ["  Action", "action", "Indie", ""]}
    )

    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == ["Action", "Indie"]
    settings = (await test_client.get("/api/v1/settings")).json()["data"]
    assert settings["excluded_genres"] == ["Action", "Indie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [
    [f"Genre {i}" for i in range(51)],
    ["x" * 65],
    "Action",
    [1, 2],
])
async def test_update_excluded_genres_invalid_leaves_row_unchanged(
    test_client: AsyncClient, value
):
    """51 items, a 65-character item or a non-list body give 422 and no write."""
    await test_client.put("/api/v1/settings", json={"excluded_genres": ["Sports"]})

    response = await test_client.put("/api/v1/settings", json={"excluded_genres": value})

    assert response.status_code == 422
    settings = (await test_client.get("/api/v1/settings")).json()["data"]
    assert settings["excluded_genres"] == ["Sports"]


@pytest.mark.asyncio
async def test_update_excluded_genres_bounds_accepted(test_client: AsyncClient):
    fifty = [f"Genre {i}" for i in range(50)]
    response = await test_client.put("/api/v1/settings", json={"excluded_genres": fifty})
    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == fifty

    response = await test_client.put("/api/v1/settings", json={"excluded_genres": ["x" * 64]})
    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == ["x" * 64]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
async def test_update_genre_list_empty_clears_and_omitted_keeps(test_client: AsyncClient, field):
    """[] clears the list; omitted leaves it unchanged."""
    await test_client.put("/api/v1/settings", json={field: ["Sports", "Racing"]})

    response = await test_client.put("/api/v1/settings", json={"autojoin_min_price": 30})
    assert response.json()["data"][field] == ["Sports", "Racing"]

    response = await test_client.put("/api/v1/settings", json={field: []})
    assert response.status_code == 200
    assert response.json()["data"][field] == []


@pytest.mark.asyncio
async def test_update_included_genres_normalizes(test_client: AsyncClient):
    response = await test_client.put("/api/v1/settings", json={"included_genres": [" RPG", "rpg", "Indie", ""]})

    assert response.status_code == 200
    assert (await _settings(test_client))["included_genres"] == ["RPG", "Indie"]


@pytest.mark.asyncio
@pytest.mark.parametrize("value, message", [
    (["x" * 65], "64"),
    ([f"Genre {i}" for i in range(51)], "50"),
    ("RPG", None),
    ([1], None),
])
async def test_update_included_genres_invalid_is_422_naming_the_field(test_client: AsyncClient, value, message):
    await test_client.put("/api/v1/settings", json={"included_genres": ["RPG"]})

    response = await test_client.put("/api/v1/settings", json={"included_genres": value})

    assert response.status_code == 422
    body = str(response.json())
    assert "included_genres" in body
    if message:
        assert message in body
    assert (await _settings(test_client))["included_genres"] == ["RPG"]


@pytest.mark.asyncio
async def test_update_overlapping_genre_lists_is_legal(test_client: AsyncClient):
    response = await test_client.put(
        "/api/v1/settings", json={"excluded_genres": ["Action"], "included_genres": ["Action"]}
    )

    assert response.status_code == 200
    settings = await _settings(test_client)
    assert (settings["excluded_genres"], settings["included_genres"]) == (["Action"], ["Action"])


@pytest.mark.asyncio
async def test_reset_restores_the_auto_join_defaults(test_client: AsyncClient):
    await test_client.put("/api/v1/settings", json={
        "excluded_genres": ["Sports"], "included_genres": ["RPG"], "autojoin_priorities": [],
        "max_entries_per_cycle": 3, "autojoin_min_score": None, "autojoin_min_reviews": None,
    })

    response = await test_client.post("/api/v1/settings/reset")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["excluded_genres"] == []
    assert data["included_genres"] == []
    assert data["autojoin_priorities"] == [{"type": "wishlist"}]
    assert data["max_entries_per_cycle"] == 10
    assert (data["autojoin_min_score"], data["autojoin_min_reviews"]) == (7, 1000)


@pytest.mark.asyncio
async def test_get_settings_fresh_database_excluded_genres_empty(test_client: AsyncClient):
    """A brand-new database answers excluded_genres [] (never null)."""
    response = await test_client.get("/api/v1/settings")

    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == []


@pytest.mark.asyncio
async def test_update_excluded_genres_limits_apply_after_normalization(test_client: AsyncClient):
    """Order of normalization is strip, drop empties, length check, dedupe,
    count check: 50 distinct names padded with duplicates and empty strings
    (100+ raw items) are accepted, and a 64-character name with surrounding
    whitespace is accepted (its length is measured after strip)."""
    fifty = [f"Genre {i}" for i in range(50)]
    raw = fifty + [g.upper() for g in fifty] + ["", "   "]

    response = await test_client.put("/api/v1/settings", json={"excluded_genres": raw})
    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == fifty

    padded = "  " + "x" * 64 + "  "
    response = await test_client.put("/api/v1/settings", json={"excluded_genres": [padded]})
    assert response.status_code == 200
    assert response.json()["data"]["excluded_genres"] == ["x" * 64]


@pytest.mark.asyncio
async def test_update_excluded_genres_51_after_dedupe_rejected(test_client: AsyncClient):
    """51 distinct names stay over the cap even when duplicates are mixed in:
    422 with the standard validation body and no write."""
    await test_client.put("/api/v1/settings", json={"excluded_genres": ["Sports"]})
    raw = [f"Genre {i}" for i in range(51)] + ["genre 0", ""]

    response = await test_client.put("/api/v1/settings", json={"excluded_genres": raw})

    assert response.status_code == 422
    body = response.json()
    assert body.get("success") is not True
    settings = (await test_client.get("/api/v1/settings")).json()["data"]
    assert settings["excluded_genres"] == ["Sports"]


async def _corrupt_stored_column(async_engine, field: str, value: object) -> None:
    """Simulate a manual database edit no API write can produce."""
    maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        settings = await SettingsRepository(session).get_settings()
        setattr(settings, field, value)
        await session.commit()


def _assert_config_error(response, *fragments: str) -> str:
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "CONFIG_002"
    for fragment in fragments:
        assert fragment in error["message"]
    return error["message"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("autojoin_priorities", [{"type": "bogus"}], "unknown priority type 'bogus'"),
        ("excluded_genres", ["x" * 65], "each excluded_genres item must be at most 64 characters"),
        ("included_genres", [f"genre {i}" for i in range(51)], "included_genres accepts at most 50 genres"),
    ],
)
async def test_get_settings_with_a_corrupt_stored_column_names_it(
    test_client: AsyncClient, async_engine, field, value, problem
):
    await test_client.put("/api/v1/settings", json={"phpsessid": "secret-session"})
    await _corrupt_stored_column(async_engine, field, value)

    response = await test_client.get("/api/v1/settings")

    message = _assert_config_error(response, problem, "POST /api/v1/settings/reset")
    assert "secret-session" not in response.text
    assert "secret-session" not in message


@pytest.mark.asyncio
async def test_put_over_a_corrupt_list_writes_nothing_unless_it_replaces_it(test_client: AsyncClient, async_engine):
    await _corrupt_stored_column(async_engine, "autojoin_priorities", [{"type": "bogus"}])

    refused = await test_client.put("/api/v1/settings", json={"autojoin_min_price": 99})
    _assert_config_error(refused, "unknown priority type 'bogus'")

    repaired = await test_client.put("/api/v1/settings", json={"autojoin_priorities": [{"type": "dlc"}]})
    assert repaired.status_code == 200
    assert repaired.json()["data"]["autojoin_priorities"] == [{"type": "dlc"}]
    assert repaired.json()["data"]["autojoin_min_price"] == 10
    assert (await test_client.get("/api/v1/settings")).status_code == 200


@pytest.mark.asyncio
async def test_credentials_over_a_corrupt_list_write_nothing_and_reset_repairs(
    test_client: AsyncClient, async_engine
):
    await test_client.put("/api/v1/settings", json={"phpsessid": "old-session"})
    await _corrupt_stored_column(async_engine, "autojoin_priorities", [{"type": "bogus"}])

    refused = await test_client.post("/api/v1/settings/credentials", json={"phpsessid": "new-session"})
    _assert_config_error(refused, "unknown priority type 'bogus'")
    assert "new-session" not in refused.text
    assert "old-session" not in refused.text

    reset = await test_client.post("/api/v1/settings/reset")
    assert reset.status_code == 200
    data = reset.json()["data"]
    assert data["phpsessid"] == "old-session"
    assert data["autojoin_priorities"] == [{"type": "wishlist"}]


# ==================== QA: contract gaps (test engineer) ====================

@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
@pytest.mark.parametrize("value, message", [
    (["x" * 65], "each {field} item must be at most 64 characters"),
    ([f"Genre {i}" for i in range(51)], "{field} accepts at most 50 genres"),
])
async def test_genre_list_422_messages_name_the_list(test_client: AsyncClient, field, value, message):
    """The 422 message names the list that broke the rule (not a generic one)."""
    response = await test_client.put("/api/v1/settings", json={field: value})

    assert response.status_code == 422
    assert message.format(field=field) in response.text
    other = "included_genres" if field == "excluded_genres" else "excluded_genres"
    assert f"{other} accepts" not in response.text and f"each {other} item" not in response.text


@pytest.mark.asyncio
async def test_null_genre_list_with_a_valid_other_list_writes_neither(test_client: AsyncClient):
    await test_client.put("/api/v1/settings", json={"excluded_genres": ["Sports"], "included_genres": ["RPG"]})

    response = await test_client.put("/api/v1/settings", json={"included_genres": None, "excluded_genres": ["Racing"]})

    assert response.status_code == 400
    assert response.json()["detail"] == "included_genres cannot be null"
    settings = await _settings(test_client)
    assert (settings["excluded_genres"], settings["included_genres"]) == (["Sports"], ["RPG"])


@pytest.mark.asyncio
async def test_reset_after_a_saved_include_list_empties_it(test_client: AsyncClient):
    await test_client.put("/api/v1/settings", json={"included_genres": ["RPG", "Indie"]})

    await test_client.post("/api/v1/settings/reset")

    assert (await _settings(test_client))["included_genres"] == []
