"""API schemas for settings endpoints.

This module provides Pydantic schemas for settings-related
API requests and responses.
"""

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from services.eligibility import (
    GENRE_LIST_MAX_ITEMS,
    GENRE_NAME_MAX_LENGTH,
    MAX_PRIORITY_ITEMS,
    THRESHOLD_MAX,
    THRESHOLD_MIN,
    normalize_genre_list,
)
from services.settings_service import normalize_priorities

EXCLUDED_GENRES_DESCRIPTION = (
    "Steam genre names auto-join skips: a giveaway whose cached game carries any of "
    "them is skipped (unknown genres pass). Matched case-insensitively."
)
INCLUDED_GENRES_DESCRIPTION = (
    "Steam genre names of which the cached game must carry at least one; empty = any "
    "genre. A game with no cached genres fails a non-empty included list."
)
GENRE_LISTS_DESCRIPTION = (
    "Exclusion wins: a genre on both lists is skipped. Wishlist and DLC items in the "
    "priority list skip both lists. At most "
    f"{GENRE_LIST_MAX_ITEMS} genres of up to {GENRE_NAME_MAX_LENGTH} characters; "
    "whitespace is stripped, empty items dropped and case-insensitive duplicates "
    "removed (first spelling kept)."
)
PRIORITIES_DESCRIPTION = (
    "Ordered auto-join priority list: matching giveaways are entered in list order, "
    "the rest after them by price. Wishlist and DLC items skip the filters; ending "
    f"soon obeys them. Each type at most once, at most {MAX_PRIORITY_ITEMS} items."
)


class WishlistPriority(BaseModel):
    """Priority item: games on the user's Steam wishlist (skips the filters)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["wishlist"]


class DlcPriority(BaseModel):
    """Priority item: DLC for games the user owns (skips the filters)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["dlc"]


class EndingSoonPriority(BaseModel):
    """Priority item: giveaways ending within the threshold (obeys the filters)."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["ending_soon"]
    threshold_minutes: int = Field(
        ...,
        ge=THRESHOLD_MIN,
        le=THRESHOLD_MAX,
        description="Minutes before the end within which a giveaway counts as ending soon",
        examples=[60],
    )


AutojoinPriorityItem = Annotated[
    WishlistPriority | DlcPriority | EndingSoonPriority, Field(discriminator="type")
]

# The seven policy fields' types, shared by settings and the preview request
# so both validate identically.
MinPrice = Annotated[int, Field(ge=0)]
MinScore = Annotated[int | None, Field(ge=0, le=10)]
MinReviews = Annotated[int | None, Field(ge=0)]
MaxGameAge = Annotated[int | None, Field(ge=1)]
GenreList = list[str]
PriorityList = list[AutojoinPriorityItem]

MIN_PRICE_DESCRIPTION = "Minimum giveaway price in points"
MIN_SCORE_DESCRIPTION = "Minimum Steam review score (0-10); null = filter off, 0 still needs cached game data"
MIN_REVIEWS_DESCRIPTION = "Minimum number of reviews; null = filter off, 0 still needs cached game data"
MAX_GAME_AGE_DESCRIPTION = "Maximum game age in years (null = no limit)"


def _check_priorities(items: list[Any]) -> None:
    """Run the registry's list rules (duplicates, item count) on parsed items."""
    normalize_priorities([item.model_dump() for item in items])


class AutojoinPolicyFields(BaseModel):
    """The seven auto-join policy fields with their defaults and validators.

    Shared by SettingsBase (settings responses) and PolicyPreviewRequest
    (which makes all seven required), so the preview and PUT /settings accept
    exactly the same values.
    """

    autojoin_min_price: MinPrice = Field(default=10, description=MIN_PRICE_DESCRIPTION, examples=[10])
    autojoin_min_score: MinScore = Field(default=7, description=MIN_SCORE_DESCRIPTION, examples=[7])
    autojoin_min_reviews: MinReviews = Field(default=1000, description=MIN_REVIEWS_DESCRIPTION, examples=[1000])
    autojoin_max_game_age: MaxGameAge = Field(default=None, description=MAX_GAME_AGE_DESCRIPTION, examples=[5])
    excluded_genres: GenreList = Field(
        default_factory=list,
        description=f"{EXCLUDED_GENRES_DESCRIPTION} {GENRE_LISTS_DESCRIPTION}",
        examples=[["Sports", "Racing"]],
    )
    included_genres: GenreList = Field(
        default_factory=list,
        description=f"{INCLUDED_GENRES_DESCRIPTION} {GENRE_LISTS_DESCRIPTION}",
        examples=[["RPG", "Strategy"]],
    )
    autojoin_priorities: PriorityList = Field(
        default_factory=lambda: [WishlistPriority(type="wishlist")],
        description=PRIORITIES_DESCRIPTION,
        examples=[[{"type": "wishlist"}, {"type": "ending_soon", "threshold_minutes": 60}]],
    )

    @field_validator("excluded_genres", "included_genres")
    @classmethod
    def validate_genre_list(cls, v: list[str], info: ValidationInfo) -> list[str]:
        """Strip, drop empties, bound and dedupe a genre list."""
        return normalize_genre_list(v, info.field_name or "genres")

    @field_validator("autojoin_priorities")
    @classmethod
    def validate_priorities(cls, v: list[Any]) -> list[Any]:
        """Reject duplicate types and over-long lists."""
        _check_priorities(v)
        return v


class SettingsBase(AutojoinPolicyFields):
    """
    Base settings schema with common fields.

    This serves as the base for other settings schemas.
    """

    # SteamGifts Authentication
    phpsessid: str | None = Field(
        default=None,
        description="SteamGifts session cookie for authentication",
        examples=["abc123def456..."],
    )
    user_agent: str = Field(
        ...,
        description="Browser user agent string for HTTP requests",
        examples=["Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0"],
    )
    xsrf_token: str | None = Field(
        default=None,
        description="Anti-CSRF token from SteamGifts",
        examples=["xyz789..."],
    )

    # Safety Settings
    safety_check_enabled: bool = Field(
        default=True,
        description="Check giveaways for traps before auto-entering",
        examples=[True],
    )
    auto_hide_unsafe: bool = Field(
        default=True,
        description="Automatically hide unsafe giveaways on SteamGifts",
        examples=[True],
    )

    # Auto-join Settings
    autojoin_enabled: bool = Field(
        default=False,
        description="Enable automatic giveaway entry",
        examples=[True],
    )
    autojoin_start_at: int = Field(
        default=350,
        description="Start entering when points >= this value",
        ge=0,
        examples=[350],
    )
    autojoin_stop_at: int = Field(
        default=200,
        description="Stop entering when points <= this value",
        ge=0,
        examples=[200],
    )

    # Scheduler Settings
    scan_interval_minutes: int = Field(
        default=30,
        description="How often to scan for giveaways (minutes)",
        ge=1,
        examples=[30],
    )
    max_entries_per_cycle: int = Field(
        default=10,
        description="Per cycle cap on entry attempts (never unlimited)",
        ge=1,
        examples=[10],
    )
    automation_enabled: bool = Field(
        default=False,
        description="Master switch for automation",
        examples=[False],
    )

    # Advanced Settings
    max_scan_pages: int = Field(
        default=3,
        description="Maximum SteamGifts pages to scan per cycle",
        ge=1,
        examples=[3],
    )
    entry_delay_min: int = Field(
        default=8,
        description="Minimum delay between entries (seconds)",
        ge=0,
        examples=[8],
    )
    entry_delay_max: int = Field(
        default=12,
        description="Maximum delay between entries (seconds)",
        ge=0,
        examples=[12],
    )
    log_retention_days: int = Field(
        default=30,
        description="Activity logs older than this many days are pruned (0 = keep forever)",
        ge=0,
        examples=[30],
    )

    @field_validator("entry_delay_max")
    @classmethod
    def validate_delay_range(cls, v: int, info: ValidationInfo) -> int:
        """Validate that entry_delay_max >= entry_delay_min."""
        if "entry_delay_min" in info.data and v < info.data["entry_delay_min"]:
            raise ValueError("entry_delay_max must be >= entry_delay_min")
        return v

    @field_validator("autojoin_stop_at")
    @classmethod
    def validate_point_thresholds(cls, v: int, info: ValidationInfo) -> int:
        """Validate that autojoin_stop_at <= autojoin_start_at."""
        if "autojoin_start_at" in info.data and v > info.data["autojoin_start_at"]:
            raise ValueError("autojoin_stop_at must be <= autojoin_start_at")
        return v


class SettingsResponse(SettingsBase):
    """
    Settings response schema.

    Extends SettingsBase with additional metadata fields.

    Example:
        >>> settings = SettingsResponse(
        ...     id=1,
        ...     user_agent="Mozilla/5.0...",
        ...     autojoin_enabled=True,
        ...     created_at=utcnow(),
        ...     updated_at=utcnow()
        ... )
    """

    id: int = Field(
        ...,
        description="Settings ID (always 1 for singleton)",
        examples=[1],
    )
    last_synced_at: datetime | None = Field(
        default=None,
        description="Last sync with SteamGifts",
        examples=["2025-10-14T12:00:00"],
    )
    created_at: datetime = Field(
        ...,
        description="When settings were first created",
        examples=["2025-10-14T10:00:00"],
    )
    updated_at: datetime = Field(
        ...,
        description="Last time settings were modified",
        examples=["2025-10-14T12:00:00"],
    )

    model_config = {
        "from_attributes": True,  # Enable ORM mode for SQLAlchemy models
        "json_schema_extra": {
            "examples": [
                {
                    "id": 1,
                    "phpsessid": "abc123...",
                    "user_agent": "Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0",
                    "xsrf_token": None,
                    "autojoin_enabled": True,
                    "autojoin_start_at": 350,
                    "autojoin_stop_at": 200,
                    "autojoin_min_price": 10,
                    "autojoin_min_score": 7,
                    "autojoin_min_reviews": None,
                    "autojoin_max_game_age": None,
                    "excluded_genres": ["Sports", "Racing"],
                    "included_genres": ["RPG"],
                    "autojoin_priorities": [
                        {"type": "wishlist"},
                        {"type": "ending_soon", "threshold_minutes": 60},
                    ],
                    "scan_interval_minutes": 30,
                    "max_entries_per_cycle": 10,
                    "automation_enabled": True,
                    "max_scan_pages": 3,
                    "entry_delay_min": 8,
                    "entry_delay_max": 12,
                    "last_synced_at": "2025-10-14T12:00:00",
                    "created_at": "2025-10-14T10:00:00",
                    "updated_at": "2025-10-14T12:00:00",
                }
            ]
        },
    }


class SettingsUpdate(BaseModel):
    """
    Settings update schema.

    All fields are optional for partial updates.

    Example:
        >>> update = SettingsUpdate(
        ...     autojoin_enabled=True,
        ...     autojoin_min_price=50
        ... )
    """

    # SteamGifts Authentication
    phpsessid: str | None = Field(
        default=None,
        description="SteamGifts session cookie",
    )
    user_agent: str | None = Field(
        default=None,
        description="Browser user agent string",
    )
    xsrf_token: str | None = Field(
        default=None,
        description="Anti-CSRF token",
    )

    # Safety Settings
    safety_check_enabled: bool | None = Field(
        default=None,
        description="Check giveaways for traps before auto-entering",
    )
    auto_hide_unsafe: bool | None = Field(
        default=None,
        description="Automatically hide unsafe giveaways on SteamGifts",
    )

    # Auto-join Settings
    autojoin_enabled: bool | None = Field(
        default=None,
        description="Enable automatic giveaway entry",
    )
    autojoin_start_at: int | None = Field(
        default=None,
        description="Start entering when points >= this value",
        ge=0,
    )
    autojoin_stop_at: int | None = Field(
        default=None,
        description="Stop entering when points <= this value",
        ge=0,
    )
    autojoin_min_price: int | None = Field(
        default=None,
        description="Minimum giveaway price in points",
        ge=0,
    )
    autojoin_min_score: MinScore = Field(
        default=None,
        description=f"{MIN_SCORE_DESCRIPTION}. Explicit null turns the filter off; omitted = unchanged.",
    )
    autojoin_min_reviews: MinReviews = Field(
        default=None,
        description=f"{MIN_REVIEWS_DESCRIPTION}. Explicit null turns the filter off; omitted = unchanged.",
    )
    autojoin_max_game_age: MaxGameAge = Field(
        default=None,
        description=f"{MAX_GAME_AGE_DESCRIPTION}. Explicit null removes the limit; omitted = unchanged.",
    )
    excluded_genres: GenreList | None = Field(
        default=None,
        description=f"{EXCLUDED_GENRES_DESCRIPTION} {GENRE_LISTS_DESCRIPTION} Omitted = unchanged; [] clears it.",
        examples=[["Sports", "Racing"]],
    )
    included_genres: GenreList | None = Field(
        default=None,
        description=f"{INCLUDED_GENRES_DESCRIPTION} {GENRE_LISTS_DESCRIPTION} Omitted = unchanged; [] clears it.",
        examples=[["RPG", "Strategy"]],
    )
    autojoin_priorities: PriorityList | None = Field(
        default=None,
        description=f"{PRIORITIES_DESCRIPTION} Omitted or null = unchanged; [] = no priorities.",
        examples=[[{"type": "dlc"}, {"type": "wishlist"}]],
    )

    # Scheduler Settings
    scan_interval_minutes: int | None = Field(
        default=None,
        description="How often to scan for giveaways (minutes)",
        ge=1,
    )
    max_entries_per_cycle: int | None = Field(
        default=None,
        description="Per cycle cap on entry attempts (1 or more)",
        ge=1,
    )
    automation_enabled: bool | None = Field(
        default=None,
        description="Master switch for automation",
    )

    # Advanced Settings
    max_scan_pages: int | None = Field(
        default=None,
        description="Maximum SteamGifts pages to scan per cycle",
        ge=1,
    )
    entry_delay_min: int | None = Field(
        default=None,
        description="Minimum delay between entries (seconds)",
        ge=0,
    )
    entry_delay_max: int | None = Field(
        default=None,
        description="Maximum delay between entries (seconds)",
        ge=0,
    )
    log_retention_days: int | None = Field(
        default=None,
        description="Activity logs older than this many days are pruned (0 = keep forever)",
        ge=0,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "autojoin_enabled": True,
                    "autojoin_min_price": 50,
                    "autojoin_min_reviews": None,
                    "max_entries_per_cycle": 15,
                    "excluded_genres": ["Sports", "Racing"],
                    "included_genres": [],
                    "autojoin_priorities": [{"type": "dlc"}, {"type": "wishlist"}],
                },
                {
                    "automation_enabled": True,
                    "scan_interval_minutes": 45,
                },
            ]
        }
    }

    @field_validator("excluded_genres", "included_genres")
    @classmethod
    def validate_genre_list(cls, v: list[str] | None, info: ValidationInfo) -> list[str] | None:
        """Strip, drop empties, bound and dedupe a genre list (None is left to the service)."""
        if v is None:
            return None
        return normalize_genre_list(v, info.field_name or "genres")

    @field_validator("autojoin_priorities")
    @classmethod
    def validate_priorities(cls, v: list[Any] | None) -> list[Any] | None:
        """Reject duplicate types and over-long lists (None = unchanged)."""
        if v is None:
            return None
        _check_priorities(v)
        return v


class PolicyPreviewRequest(AutojoinPolicyFields):
    """An unsaved auto-join policy for POST /giveaways/preview.

    Exactly the seven policy fields, all required; the validators are the
    ones PUT /settings runs. Unknown keys are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    autojoin_min_price: MinPrice = Field(..., description=MIN_PRICE_DESCRIPTION, examples=[10])
    autojoin_min_score: MinScore = Field(..., description=MIN_SCORE_DESCRIPTION, examples=[7])
    autojoin_min_reviews: MinReviews = Field(..., description=MIN_REVIEWS_DESCRIPTION, examples=[1000])
    autojoin_max_game_age: MaxGameAge = Field(..., description=MAX_GAME_AGE_DESCRIPTION, examples=[None])
    excluded_genres: GenreList = Field(..., description=EXCLUDED_GENRES_DESCRIPTION, examples=[["Sports"]])
    included_genres: GenreList = Field(..., description=INCLUDED_GENRES_DESCRIPTION, examples=[[]])
    autojoin_priorities: PriorityList = Field(
        ..., description=PRIORITIES_DESCRIPTION, examples=[[{"type": "wishlist"}]]
    )


class SteamGiftsCredentials(BaseModel):
    """
    Schema for setting SteamGifts credentials.

    Example:
        >>> creds = SteamGiftsCredentials(
        ...     phpsessid="abc123...",
        ...     user_agent="Mozilla/5.0..."
        ... )
    """

    phpsessid: str = Field(
        ...,
        description="SteamGifts PHPSESSID cookie",
        min_length=1,
        examples=["abc123def456..."],
    )
    user_agent: str | None = Field(
        default=None,
        description="Optional user agent string",
        examples=["Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0"],
    )

    @field_validator("phpsessid")
    @classmethod
    def validate_phpsessid(cls, v: str) -> str:
        """Validate PHPSESSID is not empty after stripping."""
        if not v or not v.strip():
            raise ValueError("phpsessid cannot be empty")
        return v.strip()


class ConfigurationValidation(BaseModel):
    """
    Schema for configuration validation results.

    Example:
        >>> result = ConfigurationValidation(
        ...     is_valid=True,
        ...     errors=[],
        ...     warnings=["Consider setting a minimum price"]
        ... )
    """

    is_valid: bool = Field(
        ...,
        description="Overall validity of configuration",
        examples=[True],
    )
    errors: list[str] = Field(
        default_factory=list,
        description="List of validation errors (blocking issues)",
        examples=[["PHPSESSID not configured"]],
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="List of warnings (non-blocking suggestions)",
        examples=[["Consider setting a minimum price"]],
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "is_valid": True,
                    "errors": [],
                    "warnings": [],
                },
                {
                    "is_valid": False,
                    "errors": ["PHPSESSID not configured"],
                    "warnings": ["Consider setting entry delays"],
                },
            ]
        }
    }
