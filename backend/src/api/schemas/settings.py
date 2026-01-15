"""API schemas for settings endpoints.

This module provides Pydantic schemas for settings-related
API requests and responses.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class SettingsBase(BaseModel):
    """
    Base settings schema with common fields.

    This serves as the base for other settings schemas.
    """

    # SteamGifts Authentication
    phpsessid: Optional[str] = Field(
        default=None,
        description="SteamGifts session cookie for authentication",
        examples=["abc123def456..."],
    )
    user_agent: str = Field(
        ...,
        description="Browser user agent string for HTTP requests",
        examples=["Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0"],
    )
    xsrf_token: Optional[str] = Field(
        default=None,
        description="Anti-CSRF token from SteamGifts",
        examples=["xyz789..."],
    )

    # DLC Settings
    dlc_enabled: bool = Field(
        default=False,
        description="Whether to enter DLC giveaways",
        examples=[False],
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
    autojoin_min_price: int = Field(
        default=10,
        description="Minimum giveaway price in points",
        ge=0,
        examples=[10],
    )
    autojoin_min_score: int = Field(
        default=7,
        description="Minimum Steam review score (0-10)",
        ge=0,
        le=10,
        examples=[7],
    )
    autojoin_min_reviews: int = Field(
        default=1000,
        description="Minimum number of reviews required",
        ge=0,
        examples=[1000],
    )
    autojoin_max_game_age: Optional[int] = Field(
        default=None,
        description="Maximum game age in years (None = no limit)",
        ge=1,
        examples=[5],
    )

    # Scheduler Settings
    scan_interval_minutes: int = Field(
        default=30,
        description="How often to scan for giveaways (minutes)",
        ge=1,
        examples=[30],
    )
    max_entries_per_cycle: Optional[int] = Field(
        default=None,
        description="Max entries per scan cycle (None = unlimited)",
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

    @field_validator("entry_delay_max")
    @classmethod
    def validate_delay_range(cls, v, info):
        """Validate that entry_delay_max >= entry_delay_min."""
        if "entry_delay_min" in info.data and v < info.data["entry_delay_min"]:
            raise ValueError("entry_delay_max must be >= entry_delay_min")
        return v

    @field_validator("autojoin_stop_at")
    @classmethod
    def validate_point_thresholds(cls, v, info):
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
        ...     created_at=datetime.utcnow(),
        ...     updated_at=datetime.utcnow()
        ... )
    """

    id: int = Field(
        ...,
        description="Settings ID (always 1 for singleton)",
        examples=[1],
    )
    last_synced_at: Optional[datetime] = Field(
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
                    "dlc_enabled": False,
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
    phpsessid: Optional[str] = Field(
        default=None,
        description="SteamGifts session cookie",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Browser user agent string",
    )
    xsrf_token: Optional[str] = Field(
        default=None,
        description="Anti-CSRF token",
    )

    # DLC Settings
    dlc_enabled: Optional[bool] = Field(
        default=None,
        description="Whether to enter DLC giveaways",
    )

    # Safety Settings
    safety_check_enabled: Optional[bool] = Field(
        default=None,
        description="Check giveaways for traps before auto-entering",
    )
    auto_hide_unsafe: Optional[bool] = Field(
        default=None,
        description="Automatically hide unsafe giveaways on SteamGifts",
    )

    # Auto-join Settings
    autojoin_enabled: Optional[bool] = Field(
        default=None,
        description="Enable automatic giveaway entry",
    )
    autojoin_start_at: Optional[int] = Field(
        default=None,
        description="Start entering when points >= this value",
        ge=0,
    )
    autojoin_stop_at: Optional[int] = Field(
        default=None,
        description="Stop entering when points <= this value",
        ge=0,
    )
    autojoin_min_price: Optional[int] = Field(
        default=None,
        description="Minimum giveaway price in points",
        ge=0,
    )
    autojoin_min_score: Optional[int] = Field(
        default=None,
        description="Minimum Steam review score (0-10)",
        ge=0,
        le=10,
    )
    autojoin_min_reviews: Optional[int] = Field(
        default=None,
        description="Minimum number of reviews required",
        ge=0,
    )
    autojoin_max_game_age: Optional[int] = Field(
        default=None,
        description="Maximum game age in years (None = no limit)",
        ge=1,
    )

    # Scheduler Settings
    scan_interval_minutes: Optional[int] = Field(
        default=None,
        description="How often to scan for giveaways (minutes)",
        ge=1,
    )
    max_entries_per_cycle: Optional[int] = Field(
        default=None,
        description="Max entries per scan cycle",
        ge=1,
    )
    automation_enabled: Optional[bool] = Field(
        default=None,
        description="Master switch for automation",
    )

    # Advanced Settings
    max_scan_pages: Optional[int] = Field(
        default=None,
        description="Maximum SteamGifts pages to scan per cycle",
        ge=1,
    )
    entry_delay_min: Optional[int] = Field(
        default=None,
        description="Minimum delay between entries (seconds)",
        ge=0,
    )
    entry_delay_max: Optional[int] = Field(
        default=None,
        description="Maximum delay between entries (seconds)",
        ge=0,
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "autojoin_enabled": True,
                    "autojoin_min_price": 50,
                    "max_entries_per_cycle": 15,
                },
                {
                    "automation_enabled": True,
                    "scan_interval_minutes": 45,
                },
            ]
        }
    }


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
    user_agent: Optional[str] = Field(
        default=None,
        description="Optional user agent string",
        examples=["Mozilla/5.0 (X11; Linux x86_64) Firefox/82.0"],
    )

    @field_validator("phpsessid")
    @classmethod
    def validate_phpsessid(cls, v):
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
