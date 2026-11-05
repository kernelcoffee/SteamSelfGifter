"""Settings service with business logic for settings management.

This module provides the service layer for settings operations, adding
validation and business logic on top of the SettingsRepository.
"""

from collections.abc import Collection
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ConfigurationError, SteamGiftsAuthError, SteamGiftsError
from models.settings import Settings
from repositories.settings import SettingsRepository
from services.eligibility import (
    InvalidPolicyError,
    check_policy_column,
    normalize_genre_list,
    parse_priorities,
)
from utils.steamgifts_client import SteamGiftsClient

# Columns an explicit null may be written to through update_settings; every
# other column is NOT NULL, so null for it is rejected.
NULLABLE_FIELDS = frozenset({
    "phpsessid",
    "xsrf_token",
    "autojoin_min_score",
    "autojoin_min_reviews",
    "autojoin_max_game_age",
})
# Fields whose explicit null means "leave unchanged".
NULL_MEANS_UNCHANGED = frozenset({"autojoin_priorities"})

# The JSON policy columns the engine parses (services.eligibility).
POLICY_LIST_COLUMNS = ("autojoin_priorities", "excluded_genres", "included_genres")

DEFAULT_AUTOJOIN_PRIORITIES: list[dict[str, Any]] = [{"type": "wishlist"}]

# Error code of a stored policy column that cannot be parsed (shared with
# GiveawayQueryService.saved_policy, so every endpoint reports it alike).
INVALID_STORED_POLICY_CODE = "CONFIG_002"
STORED_POLICY_REPAIR_HINT = (
    "replace it with PUT /api/v1/settings or restore the defaults with POST /api/v1/settings/reset"
)


def normalize_priorities(values: object) -> list[dict[str, Any]]:
    """Validate a priority list and return its canonical stored form.

    Wraps services.eligibility.parse_priorities, the single validation path.

    Raises:
        ValueError: on any list parse_priorities rejects.

    Example:
        >>> normalize_priorities([{"type": "ending_soon", "threshold_minutes": 90}])
        [{'type': 'ending_soon', 'threshold_minutes': 90}]
    """
    return [item.to_dict() for item in parse_priorities(values)]


def check_stored_policy(settings: Settings, replaced: Collection[str] = ()) -> None:
    """Refuse a stored policy column that a settings response cannot carry.

    The JSON columns autojoin_priorities, excluded_genres and included_genres
    are validated on every write through the API, so only a manual database
    edit can leave one unparseable. SettingsResponse re-validates them, so
    such a row would otherwise surface as a generic 500 with no cause, or as a
    500 after a write that already committed.

    Args:
        settings: the stored settings row.
        replaced: fields the caller is about to overwrite; their stored values
            are not checked, so a write that repairs them goes through.

    Raises:
        ConfigurationError: CONFIG_002 naming the column, the parse error and
            the repair path. The message carries no session value.
    """
    for field_name in POLICY_LIST_COLUMNS:
        if field_name not in replaced:
            try:
                check_policy_column(field_name, getattr(settings, field_name))
            except InvalidPolicyError as e:
                raise ConfigurationError(
                    f"{e}; {STORED_POLICY_REPAIR_HINT}", code=INVALID_STORED_POLICY_CODE
                ) from e


class SettingsService:
    """
    Service for settings management.

    This service provides business logic for settings operations:
    - Settings validation
    - Authentication checks
    - Configuration retrieval
    - Settings updates with validation

    Design Notes:
        - Thin wrapper around SettingsRepository
        - Adds validation and business logic
        - All methods are async
        - Settings uses singleton pattern (id=1)

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     service = SettingsService(session)
        ...     settings = await service.get_settings()
        ...     await service.update_settings(autojoin_min_price=100)
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize SettingsService.

        Args:
            session: Database session

        Example:
            >>> service = SettingsService(session)
        """
        self.session = session
        self.repo = SettingsRepository(session)

    async def get_settings(self) -> Settings:
        """
        Get application settings.

        Returns:
            Settings object (singleton)

        Example:
            >>> settings = await service.get_settings()
            >>> settings.autojoin_enabled
            True
        """
        return await self.repo.get_settings()

    async def get_valid_settings(self) -> Settings:
        """
        Get the settings row for a settings response.

        Returns:
            Settings object (singleton) whose policy columns SettingsResponse
            can carry.

        Raises:
            ConfigurationError: when a stored policy column cannot be parsed
                (see check_stored_policy).
        """
        settings = await self.repo.get_settings()
        check_stored_policy(settings)
        return settings

    async def update_settings(self, **kwargs: Any) -> Settings:
        """
        Update settings with validation.

        Args:
            **kwargs: Settings fields to update

        Returns:
            Updated Settings object

        Raises:
            ValueError: If validation fails
            ConfigurationError: when a stored policy column cannot be parsed
                and the update does not replace it; nothing is written.

        Example:
            >>> await service.update_settings(
            ...     autojoin_enabled=True,
            ...     autojoin_min_price=50
            ... )
        """
        # Null handling: omitted fields never reach here (the router dumps
        # with exclude_unset), so None is an explicit null. It means
        # "unchanged" for the priority list, NULL for the nullable columns,
        # and is rejected for every NOT NULL column.
        for key in NULL_MEANS_UNCHANGED:
            if key in kwargs and kwargs[key] is None:
                del kwargs[key]
        for key, value in kwargs.items():
            if value is None and key not in NULLABLE_FIELDS:
                raise ValueError(f"{key} cannot be null")
        if not kwargs:
            raise ValueError("No fields provided for update")

        # Validate min_price
        if "autojoin_min_price" in kwargs and kwargs["autojoin_min_price"] < 0:
            raise ValueError("autojoin_min_price must be >= 0")

        # Validate min_score (None = filter off)
        if "autojoin_min_score" in kwargs:
            min_score = kwargs["autojoin_min_score"]
            if min_score is not None and not (0 <= min_score <= 10):
                raise ValueError("autojoin_min_score must be between 0 and 10")

        # Validate min_reviews (None = filter off)
        if "autojoin_min_reviews" in kwargs:
            min_reviews = kwargs["autojoin_min_reviews"]
            if min_reviews is not None and min_reviews < 0:
                raise ValueError("autojoin_min_reviews must be >= 0")

        # Validate and normalize both genre lists and the priority list
        # (mirrors the schema validators).
        for field_name in ("excluded_genres", "included_genres"):
            if field_name in kwargs:
                kwargs[field_name] = normalize_genre_list(kwargs[field_name], field_name)
        if "autojoin_priorities" in kwargs:
            kwargs["autojoin_priorities"] = normalize_priorities(kwargs["autojoin_priorities"])

        # Validate max_scan_pages
        if "max_scan_pages" in kwargs and kwargs["max_scan_pages"] < 1:
            raise ValueError("max_scan_pages must be >= 1")

        # Validate max_entries_per_cycle (the per cycle cap; never unlimited)
        if "max_entries_per_cycle" in kwargs and kwargs["max_entries_per_cycle"] < 1:
            raise ValueError("max_entries_per_cycle must be >= 1")

        # Validate entry delays
        if "entry_delay_min" in kwargs and kwargs["entry_delay_min"] < 0:
            raise ValueError("entry_delay_min must be >= 0")

        if "entry_delay_max" in kwargs and kwargs["entry_delay_max"] < 0:
            raise ValueError("entry_delay_max must be >= 0")

        # Validate delay_min <= delay_max
        settings = await self.repo.get_settings()
        delay_min = kwargs.get("entry_delay_min", settings.entry_delay_min)
        delay_max = kwargs.get("entry_delay_max", settings.entry_delay_max)
        if delay_min is not None and delay_max is not None and delay_min > delay_max:
            raise ValueError("entry_delay_min must be <= entry_delay_max")

        check_stored_policy(settings, replaced=kwargs.keys())
        return await self.repo.update_settings(**kwargs)

    async def set_steamgifts_credentials(
        self, phpsessid: str, user_agent: str | None = None
    ) -> Settings:
        """
        Set SteamGifts credentials.

        Args:
            phpsessid: SteamGifts PHPSESSID cookie
            user_agent: Optional user agent string

        Returns:
            Updated Settings object

        Raises:
            ValueError: If phpsessid is empty
            ConfigurationError: when a stored policy column cannot be parsed;
                nothing is written.

        Example:
            >>> await service.set_steamgifts_credentials(
            ...     phpsessid="abc123...",
            ...     user_agent="Mozilla/5.0..."
            ... )
        """
        if not phpsessid or not phpsessid.strip():
            raise ValueError("phpsessid cannot be empty")

        updates = {"phpsessid": phpsessid.strip()}
        if user_agent:
            updates["user_agent"] = user_agent

        check_stored_policy(await self.repo.get_settings())
        return await self.repo.update_settings(**updates)

    async def clear_steamgifts_credentials(self) -> Settings:
        """
        Clear SteamGifts credentials.

        Returns:
            Updated Settings object

        Example:
            >>> await service.clear_steamgifts_credentials()
        """
        # Reset to default user agent (user_agent is NOT NULL with default)
        default_user_agent = "Mozilla/5.0 (X11; Fedora; Linux x86_64; rv:82.0) Gecko/20100101 Firefox/82.0"
        return await self.repo.update_settings(
            phpsessid=None,
            user_agent=default_user_agent,
            xsrf_token=None
        )

    async def is_authenticated(self) -> bool:
        """
        Check if SteamGifts is authenticated.

        Returns:
            True if PHPSESSID is set, False otherwise

        Example:
            >>> is_auth = await service.is_authenticated()
            >>> if not is_auth:
            ...     print("Please configure SteamGifts credentials")
        """
        return await self.repo.is_authenticated()

    async def get_scheduler_config(self) -> dict[str, Any]:
        """
        Get scheduler configuration.

        Returns:
            Dictionary with scheduler settings

        Example:
            >>> config = await service.get_scheduler_config()
            >>> config['scan_interval_minutes']
            30
        """
        return await self.repo.get_scheduler_config()

    async def reset_to_defaults(self) -> Settings:
        """
        Reset all settings to default values.

        Keeps credentials but resets all configuration.

        Returns:
            Updated Settings object

        Example:
            >>> await service.reset_to_defaults()
        """
        settings = await self.repo.get_settings()

        # Keep credentials
        phpsessid = settings.phpsessid
        user_agent = settings.user_agent
        xsrf_token = settings.xsrf_token

        # Reset to defaults (matching Settings model defaults)
        return await self.repo.update_settings(
            # Keep credentials
            phpsessid=phpsessid,
            user_agent=user_agent,
            xsrf_token=xsrf_token,
            # Reset autojoin settings
            autojoin_enabled=False,
            autojoin_start_at=350,  # Integer default (point threshold)
            autojoin_stop_at=200,   # Integer default (point threshold)
            autojoin_min_price=10,  # Integer default
            autojoin_min_score=7,   # Integer default
            autojoin_min_reviews=1000,  # Integer default
            excluded_genres=[],
            included_genres=[],
            autojoin_priorities=list(DEFAULT_AUTOJOIN_PRIORITIES),
            # Reset scheduler settings
            scan_interval_minutes=30,
            max_entries_per_cycle=10,  # the per cycle cap
            automation_enabled=False,
            # Reset advanced settings
            max_scan_pages=3,
            entry_delay_min=8,   # Integer default
            entry_delay_max=12,  # Integer default
        )

    async def validate_configuration(self) -> dict[str, Any]:
        """
        Validate current configuration.

        Returns:
            Dictionary with validation results:
                - is_valid: Overall validity
                - errors: List of validation errors
                - warnings: List of warnings

        Example:
            >>> result = await service.validate_configuration()
            >>> if not result['is_valid']:
            ...     print(f"Errors: {result['errors']}")
        """
        settings = await self.repo.get_settings()
        errors: list[str] = []
        warnings: list[str] = []

        # Check authentication
        if not settings.phpsessid:
            errors.append("SteamGifts PHPSESSID not configured")

        # Check autojoin configuration
        if settings.autojoin_enabled:
            if settings.autojoin_min_price is None:
                warnings.append("autojoin_min_price not set, will use 0")
            for field_name in POLICY_LIST_COLUMNS:
                try:
                    check_policy_column(field_name, getattr(settings, field_name))
                except InvalidPolicyError as e:
                    errors.append(str(e))

        # Check automation configuration
        if settings.automation_enabled:
            if not settings.phpsessid:
                errors.append("Cannot enable automation without PHPSESSID")

        # Check delay configuration
        if settings.entry_delay_min and settings.entry_delay_max:
            if settings.entry_delay_min > settings.entry_delay_max:
                errors.append(
                    f"entry_delay_min ({settings.entry_delay_min}) > "
                    f"entry_delay_max ({settings.entry_delay_max})"
                )

        return {
            "is_valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }

    async def test_session(self) -> dict[str, Any]:
        """
        Test if the configured PHPSESSID is valid.

        Returns:
            Dictionary with:
                - valid: Whether the session is valid
                - username: SteamGifts username (if valid)
                - points: Current points (if valid)
                - error: Error message (if invalid)

        Example:
            >>> result = await service.test_session()
            >>> if result['valid']:
            ...     print(f"Logged in as {result['username']}")
        """
        settings = await self.repo.get_settings()

        if not settings.phpsessid:
            return {
                "valid": False,
                "error": "PHPSESSID not configured"
            }

        try:
            client = SteamGiftsClient(
                phpsessid=settings.phpsessid,
                user_agent=settings.user_agent,
                xsrf_token=settings.xsrf_token,
            )

            async with client:
                user_info = await client.get_user_info()

                # Save the XSRF token if we got a new one
                if client.xsrf_token and client.xsrf_token != settings.xsrf_token:
                    await self.repo.update_settings(xsrf_token=client.xsrf_token)

                return {
                    "valid": True,
                    "username": user_info["username"],
                    "points": user_info["points"],
                }

        except SteamGiftsAuthError as e:
            return {
                "valid": False,
                "error": str(e)
            }
        except SteamGiftsError as e:
            return {
                "valid": False,
                "error": f"SteamGifts error: {e}"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Connection error: {e}"
            }
