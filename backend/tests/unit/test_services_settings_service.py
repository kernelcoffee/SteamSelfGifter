"""Unit tests for SettingsService."""

import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.exceptions import ConfigurationError
from models.base import Base
from models.settings import Settings
from services.eligibility import normalize_genre_list
from services.settings_service import (
    SettingsService,
    check_stored_policy,
    normalize_priorities,
)


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
            max_scan_pages=10,
            autojoin_min_score=None,
            autojoin_min_reviews=None,
            max_entries_per_cycle=3,
            autojoin_priorities=[{"type": "ending_soon", "threshold_minutes": 120}],
            excluded_genres=["Sports"],
            included_genres=["RPG"],
        )
        assert (await service.get_settings()).autojoin_priorities == [
            {"type": "ending_soon", "threshold_minutes": 120}
        ]
        assert (await service.get_settings()).included_genres == ["RPG"]

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
        assert settings.max_entries_per_cycle == 10
        assert settings.autojoin_priorities == [{"type": "wishlist"}]
        assert settings.excluded_genres == []
        assert settings.included_genres == []


GENRE_FIELDS = ["excluded_genres", "included_genres"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GENRE_FIELDS)
@pytest.mark.parametrize("value, match", [
    ([f"Genre {i}" for i in range(51)], "{field} accepts at most 50 genres"),
    (["x" * 65], "each {field} item must be at most 64 characters"),
    ([" " + "x" * 65 + " "], "each {field} item must be at most 64 characters"),
    ("Action", "{field} must be a list of strings"),
    ([1, 2], "{field} must be a list of strings"),
    (None, "{field} cannot be null"),
])
async def test_update_settings_rejects_invalid_genre_lists(test_db, field, value, match):
    """Too many items, an over-long item, a non-list or null raise ValueError
    naming the field (400 via the router) and nothing is written."""
    async with test_db() as session:
        service = SettingsService(session)
        await service.update_settings(**{field: ["Sports"]})

        with pytest.raises(ValueError, match=match.format(field=field)):
            await service.update_settings(**{field: value})

        assert getattr(await service.get_settings(), field) == ["Sports"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GENRE_FIELDS)
async def test_update_settings_normalizes_genre_lists(test_db, field):
    """Items are stripped, empties dropped and case-insensitive duplicates
    removed keeping the first spelling and the user's order."""
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.update_settings(
            **{field: [" Action", "action", "  ", "Indie ", "", "ACTION", "Racing"]}
        )

        assert getattr(settings, field) == ["Action", "Indie", "Racing"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GENRE_FIELDS)
async def test_update_settings_accepts_genre_list_bounds(test_db, field):
    """Exactly 50 items and a 64-character item are accepted; 50 items
    that collapse from more duplicates are accepted too."""
    async with test_db() as session:
        service = SettingsService(session)
        fifty = [f"Genre {i}" for i in range(50)]

        assert getattr(await service.update_settings(**{field: fifty}), field) == fifty
        settings = await service.update_settings(**{field: fifty + [g.upper() for g in fifty]})
        assert getattr(settings, field) == fifty
        settings = await service.update_settings(**{field: ["x" * 64]})
        assert getattr(settings, field) == ["x" * 64]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", GENRE_FIELDS)
async def test_update_settings_empty_genre_list_clears(test_db, field):
    async with test_db() as session:
        service = SettingsService(session)
        await service.update_settings(**{field: ["Sports", "Racing"]})

        settings = await service.update_settings(**{field: []})

        assert getattr(settings, field) == []


@pytest.mark.asyncio
async def test_update_settings_accepts_overlapping_genre_lists(test_db):
    """A genre on both lists is legal; exclusion wins at evaluation time."""
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.update_settings(excluded_genres=["Action"], included_genres=["Action"])

        assert (settings.excluded_genres, settings.included_genres) == (["Action"], ["Action"])


@pytest.mark.asyncio
async def test_update_settings_stores_the_priority_list_in_order(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        priorities = [{"type": "dlc"}, {"type": "ending_soon", "threshold_minutes": 120}, {"type": "wishlist"}]

        settings = await service.update_settings(autojoin_priorities=priorities)

        assert settings.autojoin_priorities == priorities
        assert (await service.update_settings(autojoin_priorities=[])).autojoin_priorities == []


@pytest.mark.asyncio
@pytest.mark.parametrize("value, match", [
    ([{"type": "wishlist"}, {"type": "wishlist"}], "duplicate"),
    ([{"type": "ending_soon", "threshold_minutes": 4}], "between 5 and 10080"),
    ([{"type": "bogus"}], "unknown priority type"),
    ("wishlist", "must be a list"),
])
async def test_update_settings_rejects_a_bad_priority_list(test_db, value, match):
    """The service applies the registry's parser (400 via the router) and
    leaves the stored list unchanged."""
    async with test_db() as session:
        service = SettingsService(session)
        await service.update_settings(autojoin_priorities=[{"type": "dlc"}])

        with pytest.raises(ValueError, match=match):
            await service.update_settings(autojoin_priorities=value, autojoin_enabled=True)

        settings = await service.get_settings()
        assert settings.autojoin_priorities == [{"type": "dlc"}]
        assert settings.autojoin_enabled is False


@pytest.mark.asyncio
async def test_update_settings_null_priority_list_means_unchanged(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        await service.update_settings(autojoin_priorities=[{"type": "dlc"}])

        settings = await service.update_settings(autojoin_priorities=None, autojoin_enabled=True)

        assert settings.autojoin_priorities == [{"type": "dlc"}]
        assert settings.autojoin_enabled is True
        with pytest.raises(ValueError, match="No fields provided for update"):
            await service.update_settings(autojoin_priorities=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "autojoin_min_score", "autojoin_min_reviews", "autojoin_max_game_age", "phpsessid", "xsrf_token",
])
async def test_update_settings_stores_null_for_nullable_fields(test_db, field):
    async with test_db() as session:
        service = SettingsService(session)
        await service.update_settings(autojoin_min_score=0, autojoin_min_reviews=0, autojoin_max_game_age=3)
        await service.set_steamgifts_credentials(phpsessid="session")

        settings = await service.update_settings(**{field: None})

        assert getattr(settings, field) is None


@pytest.mark.asyncio
async def test_update_settings_keeps_zero_thresholds(test_db):
    async with test_db() as session:
        service = SettingsService(session)

        settings = await service.update_settings(autojoin_min_score=0, autojoin_min_reviews=0)

        assert (settings.autojoin_min_score, settings.autojoin_min_reviews) == (0, 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("field", [
    "user_agent", "max_entries_per_cycle", "autojoin_start_at", "autojoin_enabled", "entry_delay_min",
])
async def test_update_settings_rejects_null_for_not_null_fields(test_db, field):
    async with test_db() as session:
        service = SettingsService(session)
        before = getattr(await service.get_settings(), field)

        with pytest.raises(ValueError, match=f"{field} cannot be null"):
            await service.update_settings(**{field: None}, autojoin_min_price=99)

        settings = await service.get_settings()
        assert getattr(settings, field) == before
        assert settings.autojoin_min_price == 10


@pytest.mark.asyncio
async def test_update_settings_with_nothing_raises(test_db):
    async with test_db() as session:
        with pytest.raises(ValueError, match="No fields provided for update"):
            await SettingsService(session).update_settings()


def test_normalize_priorities_returns_the_canonical_form():
    assert normalize_priorities([{"type": "ending_soon", "threshold_minutes": 90}, {"type": "wishlist"}]) == [
        {"type": "ending_soon", "threshold_minutes": 90}, {"type": "wishlist"},
    ]
    with pytest.raises(ValueError, match="duplicate"):
        normalize_priorities([{"type": "dlc"}, {"type": "dlc"}])


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


@pytest.mark.asyncio
async def test_validate_configuration_reports_a_bad_stored_priority_list(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        await service.set_steamgifts_credentials(phpsessid="test_session")
        await service.update_settings(autojoin_enabled=True)
        settings = await service.get_settings()
        settings.autojoin_priorities = [{"type": "bogus"}]
        await session.commit()

        result = await service.validate_configuration()

        assert result["is_valid"] is False
        assert "Auto-join priorities setting is invalid: unknown priority type 'bogus'" in result["errors"]


@pytest.mark.asyncio
async def test_validate_configuration_ignores_the_list_while_autojoin_is_off(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        await service.set_steamgifts_credentials(phpsessid="test_session")
        settings = await service.get_settings()
        settings.autojoin_priorities = [{"type": "bogus"}]
        await session.commit()

        assert (await service.validate_configuration())["is_valid"] is True


@pytest.mark.parametrize("field", GENRE_FIELDS)
def test_normalize_genre_list_dedupes_with_the_match_fold(field):
    """Dedupe uses the same ASCII-only fold as the eligibility match, so
    spellings that match differently ("Éducation"/"éducation") are both kept
    while ASCII case variants are merged."""
    assert normalize_genre_list(["Éducation", "éducation", "ACTION", "action"], field) == [
        "Éducation", "éducation", "ACTION",
    ]


# A stored policy column that only a manual database edit can produce, with
# the problem the CONFIG_002 message must name.
CORRUPT_STORED_POLICY = [
    ("autojoin_priorities", [{"type": "bogus"}], "Auto-join priorities setting is invalid: unknown priority type 'bogus'"),
    ("autojoin_priorities", [{"type": "dlc"}, {"type": "dlc"}], "duplicate priority type 'dlc'"),
    ("autojoin_priorities", "wishlist", "autojoin_priorities must be a list"),
    ("excluded_genres", ["x" * 65], "Genre list setting is invalid: each excluded_genres item must be at most 64"),
    ("included_genres", [f"genre {i}" for i in range(51)], "included_genres accepts at most 50 genres"),
    ("included_genres", "RPG", "included_genres must be a list of strings"),
]


async def _corrupt(session: AsyncSession, field: str, value: object) -> None:
    settings = await SettingsService(session).get_settings()
    setattr(settings, field, value)
    await session.commit()


@pytest.mark.parametrize(("field", "value", "problem"), CORRUPT_STORED_POLICY)
@pytest.mark.asyncio
async def test_get_valid_settings_names_a_corrupt_stored_column(test_db, field, value, problem):
    async with test_db() as session:
        service = SettingsService(session)
        await service.set_steamgifts_credentials(phpsessid="secret-session")
        await _corrupt(session, field, value)

        with pytest.raises(ConfigurationError) as excinfo:
            await service.get_valid_settings()

    assert excinfo.value.code == "CONFIG_002"
    assert problem in excinfo.value.message
    assert "POST /api/v1/settings/reset" in excinfo.value.message
    assert "secret-session" not in excinfo.value.message


@pytest.mark.asyncio
async def test_get_valid_settings_returns_a_valid_row(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        settings = await service.get_valid_settings()

        assert settings.id == 1
        assert settings.autojoin_priorities == [{"type": "wishlist"}]


@pytest.mark.parametrize(("field", "value", "problem"), CORRUPT_STORED_POLICY)
@pytest.mark.asyncio
async def test_update_not_replacing_a_corrupt_column_writes_nothing(test_db, field, value, problem):
    async with test_db() as session:
        await _corrupt(session, field, value)
        with pytest.raises(ConfigurationError, match=re.escape(problem)):
            await SettingsService(session).update_settings(autojoin_min_price=99, autojoin_enabled=True)

    async with test_db() as session:
        stored = await SettingsService(session).get_settings()
        assert stored.autojoin_min_price == 10
        assert stored.autojoin_enabled is False
        assert getattr(stored, field) == value


@pytest.mark.parametrize(
    ("field", "value", "replacement"),
    [
        ("autojoin_priorities", [{"type": "bogus"}], [{"type": "dlc"}]),
        ("excluded_genres", ["x" * 65], ["Action"]),
        ("included_genres", "RPG", ["RPG"]),
    ],
)
@pytest.mark.asyncio
async def test_update_replacing_the_corrupt_column_repairs_it(test_db, field, value, replacement):
    async with test_db() as session:
        await _corrupt(session, field, value)
        service = SettingsService(session)
        await service.update_settings(**{field: replacement, "autojoin_min_price": 99})

        repaired = await service.get_valid_settings()
        assert getattr(repaired, field) == replacement
        assert repaired.autojoin_min_price == 99


@pytest.mark.asyncio
async def test_update_replacing_one_column_still_refuses_another_corrupt_one(test_db):
    async with test_db() as session:
        await _corrupt(session, "autojoin_priorities", [{"type": "bogus"}])
        await _corrupt(session, "excluded_genres", ["x" * 65])

        with pytest.raises(ConfigurationError, match="excluded_genres"):
            await SettingsService(session).update_settings(autojoin_priorities=[{"type": "dlc"}])

    async with test_db() as session:
        assert (await SettingsService(session).get_settings()).autojoin_priorities == [{"type": "bogus"}]


@pytest.mark.asyncio
async def test_set_credentials_over_a_corrupt_column_writes_nothing(test_db):
    async with test_db() as session:
        service = SettingsService(session)
        await service.set_steamgifts_credentials(phpsessid="old-session")
        await _corrupt(session, "autojoin_priorities", [{"type": "bogus"}])

        with pytest.raises(ConfigurationError) as excinfo:
            await service.set_steamgifts_credentials(phpsessid="new-session")

    assert "new-session" not in excinfo.value.message
    assert "old-session" not in excinfo.value.message
    async with test_db() as session:
        assert (await SettingsService(session).get_settings()).phpsessid == "old-session"


@pytest.mark.asyncio
async def test_reset_repairs_every_corrupt_column(test_db):
    async with test_db() as session:
        await _corrupt(session, "autojoin_priorities", [{"type": "bogus"}])
        await _corrupt(session, "excluded_genres", ["x" * 65])
        await _corrupt(session, "included_genres", "RPG")
        service = SettingsService(session)

        await service.reset_to_defaults()

        repaired = await service.get_valid_settings()
        assert repaired.autojoin_priorities == [{"type": "wishlist"}]
        assert repaired.excluded_genres == []
        assert repaired.included_genres == []


def test_check_stored_policy_skips_only_the_replaced_columns():
    row = Settings(autojoin_priorities=[{"type": "bogus"}], excluded_genres=["Action"], included_genres=[])

    check_stored_policy(row, replaced={"autojoin_priorities"})
    with pytest.raises(ConfigurationError, match="unknown priority type"):
        check_stored_policy(row, replaced={"excluded_genres", "included_genres"})


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["excluded_genres", "included_genres"])
async def test_validate_configuration_reports_a_bad_stored_genre_list(test_db, field):
    async with test_db() as session:
        service = SettingsService(session)
        await service.set_steamgifts_credentials(phpsessid="test_session")
        await service.update_settings(autojoin_enabled=True)
        settings = await service.get_settings()
        setattr(settings, field, "Action")
        await session.commit()

        result = await service.validate_configuration()

        assert result["is_valid"] is False
        assert f"Genre list setting is invalid: {field} must be a list of strings" in result["errors"]
