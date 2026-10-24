"""Unit tests for settings API schemas."""


import pytest
from pydantic import ValidationError

from api.schemas.settings import (
    ConfigurationValidation,
    SettingsBase,
    SettingsResponse,
    SettingsUpdate,
    SteamGiftsCredentials,
)
from core.time import utcnow


def test_settings_base_defaults():
    """Test SettingsBase with default values."""
    settings = SettingsBase(
        user_agent="Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0"
    )

    assert settings.phpsessid is None
    assert settings.dlc_priority_enabled is False
    assert settings.autojoin_enabled is False
    assert settings.autojoin_start_at == 350
    assert settings.autojoin_stop_at == 200
    assert settings.automation_enabled is False
    assert settings.ending_soon_priority_enabled is False
    assert settings.ending_soon_threshold_minutes == 60
    assert settings.excluded_genres == []


def test_excluded_genres_update_normalizes():
    """Strip, drop empties, dedupe case-insensitively keeping the first spelling."""
    update = SettingsUpdate(excluded_genres=[" Action", "action", "Indie", "", "  "])
    assert update.excluded_genres == ["Action", "Indie"]


@pytest.mark.parametrize("value", [
    [f"Genre {i}" for i in range(51)],
    ["x" * 65],
    ["  " + "x" * 65],
    "Action",
    [1, 2],
])
def test_excluded_genres_update_rejects_invalid(value):
    """51 items, a 65-character item (after strip) and non-lists fail (422)."""
    with pytest.raises(ValidationError):
        SettingsUpdate(excluded_genres=value)


def test_excluded_genres_update_accepts_bounds():
    fifty = [f"Genre {i}" for i in range(50)]
    assert SettingsUpdate(excluded_genres=fifty).excluded_genres == fifty
    assert SettingsUpdate(excluded_genres=["x" * 64]).excluded_genres == ["x" * 64]


def test_excluded_genres_empty_list_survives_exclude_none():
    """[] clears the list, so the router's exclude_none dump must keep it;
    None (unchanged) is dropped."""
    assert SettingsUpdate(excluded_genres=[]).model_dump(exclude_none=True) == {"excluded_genres": []}
    assert SettingsUpdate(excluded_genres=None).model_dump(exclude_none=True) == {}


@pytest.mark.parametrize("value", [5, 10080])
def test_ending_soon_threshold_accepts_bounds(value):
    """5 and 10080 minutes are the inclusive bounds for both schemas."""
    assert SettingsUpdate(ending_soon_threshold_minutes=value).ending_soon_threshold_minutes == value
    base = SettingsBase(user_agent="ua", ending_soon_threshold_minutes=value)
    assert base.ending_soon_threshold_minutes == value


@pytest.mark.parametrize("value", [4, 10081])
def test_ending_soon_threshold_rejects_out_of_range(value):
    """Values just outside 5..10080 fail validation in both schemas."""
    with pytest.raises(ValidationError):
        SettingsUpdate(ending_soon_threshold_minutes=value)
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="ua", ending_soon_threshold_minutes=value)


def test_ending_soon_explicit_false_survives_exclude_none():
    """An explicit False is kept by the router's exclude_none dump."""
    update = SettingsUpdate(ending_soon_priority_enabled=False)
    assert update.model_dump(exclude_none=True) == {"ending_soon_priority_enabled": False}


def test_settings_base_custom_values():
    """Test SettingsBase with custom values."""
    settings = SettingsBase(
        user_agent="Custom Agent",
        phpsessid="abc123",
        autojoin_enabled=True,
        autojoin_min_price=50,
        max_scan_pages=5
    )

    assert settings.phpsessid == "abc123"
    assert settings.autojoin_enabled is True
    # Missing excluded_genres defaults to [] (never null in responses)
    assert settings.excluded_genres == []
    assert settings.autojoin_min_price == 50
    assert settings.max_scan_pages == 5


def test_settings_base_validates_entry_delays():
    """Test SettingsBase validates delay_min <= delay_max."""
    # Valid: delay_min <= delay_max
    settings = SettingsBase(
        user_agent="Test",
        entry_delay_min=5,
        entry_delay_max=15
    )
    assert settings.entry_delay_min == 5
    assert settings.entry_delay_max == 15

    # Invalid: delay_min > delay_max
    with pytest.raises(ValidationError, match="entry_delay_max must be >= entry_delay_min"):
        SettingsBase(
            user_agent="Test",
            entry_delay_min=20,
            entry_delay_max=10
        )


def test_settings_base_validates_point_thresholds():
    """Test SettingsBase validates stop_at <= start_at."""
    # Valid: stop_at <= start_at
    settings = SettingsBase(
        user_agent="Test",
        autojoin_start_at=350,
        autojoin_stop_at=200
    )
    assert settings.autojoin_start_at == 350
    assert settings.autojoin_stop_at == 200

    # Invalid: stop_at > start_at
    with pytest.raises(ValidationError, match="autojoin_stop_at must be <= autojoin_start_at"):
        SettingsBase(
            user_agent="Test",
            autojoin_start_at=200,
            autojoin_stop_at=350
        )


def test_settings_base_validates_min_score():
    """Test SettingsBase validates min_score range."""
    # Valid scores
    SettingsBase(user_agent="Test", autojoin_min_score=0)
    SettingsBase(user_agent="Test", autojoin_min_score=5)
    SettingsBase(user_agent="Test", autojoin_min_score=10)

    # Invalid: too low
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", autojoin_min_score=-1)

    # Invalid: too high
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", autojoin_min_score=11)


def test_settings_response_from_dict():
    """Test SettingsResponse creation from dictionary."""
    data = {
        "id": 1,
        "user_agent": "Mozilla/5.0",
        "phpsessid": "abc123",
        "dlc_priority_enabled": True,
        "autojoin_enabled": True,
        "autojoin_start_at": 350,
        "autojoin_stop_at": 200,
        "autojoin_min_price": 10,
        "autojoin_min_score": 7,
        "autojoin_min_reviews": 1000,
        "scan_interval_minutes": 30,
        "max_entries_per_cycle": 10,
        "automation_enabled": True,
        "max_scan_pages": 3,
        "entry_delay_min": 8,
        "entry_delay_max": 12,
        "last_synced_at": utcnow(),
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }

    settings = SettingsResponse(**data)

    assert settings.id == 1
    assert settings.phpsessid == "abc123"
    assert settings.autojoin_enabled is True


def test_settings_update_all_optional():
    """Test SettingsUpdate with all fields optional."""
    # Empty update is valid
    update = SettingsUpdate()
    assert update.model_dump(exclude_none=True) == {}

    # Partial update
    update = SettingsUpdate(
        autojoin_enabled=True,
        autojoin_min_price=50
    )
    dumped = update.model_dump(exclude_none=True)
    assert dumped == {"autojoin_enabled": True, "autojoin_min_price": 50}


def test_settings_update_validates_ranges():
    """Test SettingsUpdate validates field ranges."""
    # Valid values
    SettingsUpdate(autojoin_min_score=7)
    SettingsUpdate(max_scan_pages=5)
    SettingsUpdate(entry_delay_min=10)

    # Invalid: min_score too high
    with pytest.raises(ValidationError):
        SettingsUpdate(autojoin_min_score=11)

    # Invalid: max_scan_pages too low
    with pytest.raises(ValidationError):
        SettingsUpdate(max_scan_pages=0)


def test_steamgifts_credentials():
    """Test SteamGiftsCredentials schema."""
    creds = SteamGiftsCredentials(
        phpsessid="abc123",
        user_agent="Mozilla/5.0"
    )

    assert creds.phpsessid == "abc123"
    assert creds.user_agent == "Mozilla/5.0"


def test_steamgifts_credentials_strips_phpsessid():
    """Test PHPSESSID is stripped of whitespace."""
    creds = SteamGiftsCredentials(phpsessid="  abc123  ")

    assert creds.phpsessid == "abc123"


def test_steamgifts_credentials_rejects_empty():
    """Test empty PHPSESSID is rejected."""
    # Empty string caught by min_length=1
    with pytest.raises(ValidationError):
        SteamGiftsCredentials(phpsessid="")

    # Whitespace-only string caught by custom validator
    with pytest.raises(ValidationError, match="phpsessid cannot be empty"):
        SteamGiftsCredentials(phpsessid="   ")


def test_steamgifts_credentials_optional_user_agent():
    """Test user_agent is optional."""
    creds = SteamGiftsCredentials(phpsessid="abc123")

    assert creds.phpsessid == "abc123"
    assert creds.user_agent is None


def test_configuration_validation_valid():
    """Test ConfigurationValidation for valid config."""
    validation = ConfigurationValidation(
        is_valid=True,
        errors=[],
        warnings=[]
    )

    assert validation.is_valid is True
    assert len(validation.errors) == 0
    assert len(validation.warnings) == 0


def test_configuration_validation_with_errors():
    """Test ConfigurationValidation with errors."""
    validation = ConfigurationValidation(
        is_valid=False,
        errors=["PHPSESSID not configured", "Invalid delay configuration"],
        warnings=["Consider setting minimum price"]
    )

    assert validation.is_valid is False
    assert len(validation.errors) == 2
    assert "PHPSESSID not configured" in validation.errors
    assert len(validation.warnings) == 1


def test_configuration_validation_default_lists():
    """Test ConfigurationValidation uses default empty lists."""
    validation = ConfigurationValidation(is_valid=True)

    assert validation.errors == []
    assert validation.warnings == []


def test_settings_base_validates_negative_values():
    """Test SettingsBase rejects negative values."""
    # autojoin_min_price must be >= 0
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", autojoin_min_price=-10)

    # autojoin_min_reviews must be >= 0
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", autojoin_min_reviews=-100)

    # entry_delay_min must be >= 0
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", entry_delay_min=-5)


def test_settings_base_validates_minimum_values():
    """Test SettingsBase validates minimum values."""
    # scan_interval_minutes must be >= 1
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", scan_interval_minutes=0)

    # max_scan_pages must be >= 1
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", max_scan_pages=0)

    # max_entries_per_cycle must be >= 1 (if not None)
    with pytest.raises(ValidationError):
        SettingsBase(user_agent="Test", max_entries_per_cycle=0)


def test_settings_response_orm_mode():
    """Test SettingsResponse has ORM mode enabled."""
    # Verify from_attributes is in config
    assert SettingsResponse.model_config.get("from_attributes") is True
