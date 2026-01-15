"""Settings service with business logic for settings management.

This module provides the service layer for settings operations, adding
validation and business logic on top of the SettingsRepository.
"""

from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.settings import SettingsRepository
from models.settings import Settings
from utils.steamgifts_client import SteamGiftsClient
from core.exceptions import SteamGiftsAuthError, SteamGiftsError


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

    async def update_settings(self, **kwargs) -> Settings:
        """
        Update settings with validation.

        Args:
            **kwargs: Settings fields to update

        Returns:
            Updated Settings object

        Raises:
            ValueError: If validation fails

        Example:
            >>> await service.update_settings(
            ...     autojoin_enabled=True,
            ...     autojoin_min_price=50
            ... )
        """
        # Validate min_price
        if "autojoin_min_price" in kwargs:
            min_price = kwargs["autojoin_min_price"]
            if min_price is not None and min_price < 0:
                raise ValueError("autojoin_min_price must be >= 0")

        # Validate min_score
        if "autojoin_min_score" in kwargs:
            min_score = kwargs["autojoin_min_score"]
            if min_score is not None and not (0 <= min_score <= 10):
                raise ValueError("autojoin_min_score must be between 0 and 10")

        # Validate min_reviews
        if "autojoin_min_reviews" in kwargs:
            min_reviews = kwargs["autojoin_min_reviews"]
            if min_reviews is not None and min_reviews < 0:
                raise ValueError("autojoin_min_reviews must be >= 0")

        # Validate max_scan_pages
        if "max_scan_pages" in kwargs:
            max_pages = kwargs["max_scan_pages"]
            if max_pages is not None and max_pages < 1:
                raise ValueError("max_scan_pages must be >= 1")

        # Validate max_entries_per_cycle
        if "max_entries_per_cycle" in kwargs:
            max_entries = kwargs["max_entries_per_cycle"]
            if max_entries is not None and max_entries < 1:
                raise ValueError("max_entries_per_cycle must be >= 1")

        # Validate entry delays
        if "entry_delay_min" in kwargs:
            delay_min = kwargs["entry_delay_min"]
            if delay_min is not None and delay_min < 0:
                raise ValueError("entry_delay_min must be >= 0")

        if "entry_delay_max" in kwargs:
            delay_max = kwargs["entry_delay_max"]
            if delay_max is not None and delay_max < 0:
                raise ValueError("entry_delay_max must be >= 0")

        # Validate delay_min <= delay_max
        settings = await self.repo.get_settings()
        delay_min = kwargs.get("entry_delay_min", settings.entry_delay_min)
        delay_max = kwargs.get("entry_delay_max", settings.entry_delay_max)
        if delay_min is not None and delay_max is not None and delay_min > delay_max:
            raise ValueError("entry_delay_min must be <= entry_delay_max")

        return await self.repo.update_settings(**kwargs)

    async def set_steamgifts_credentials(
        self, phpsessid: str, user_agent: Optional[str] = None
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

    async def get_autojoin_config(self) -> Dict[str, Any]:
        """
        Get autojoin configuration.

        Returns:
            Dictionary with autojoin settings

        Example:
            >>> config = await service.get_autojoin_config()
            >>> config['enabled']
            True
        """
        return await self.repo.get_autojoin_config()

    async def get_scheduler_config(self) -> Dict[str, Any]:
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
            # Reset DLC settings
            dlc_enabled=False,
            # Reset autojoin settings
            autojoin_enabled=False,
            autojoin_start_at=350,  # Integer default (point threshold)
            autojoin_stop_at=200,   # Integer default (point threshold)
            autojoin_min_price=10,  # Integer default
            autojoin_min_score=7,   # Integer default
            autojoin_min_reviews=1000,  # Integer default
            # Reset scheduler settings
            scan_interval_minutes=30,
            max_entries_per_cycle=None,  # None = unlimited
            automation_enabled=False,
            # Reset advanced settings
            max_scan_pages=3,
            entry_delay_min=8,   # Integer default
            entry_delay_max=12,  # Integer default
        )

    async def validate_configuration(self) -> Dict[str, Any]:
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
        errors = []
        warnings = []

        # Check authentication
        if not settings.phpsessid:
            errors.append("SteamGifts PHPSESSID not configured")

        # Check autojoin configuration
        if settings.autojoin_enabled:
            if settings.autojoin_min_price is None:
                warnings.append("autojoin_min_price not set, will use 0")

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

    async def test_session(self) -> Dict[str, Any]:
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
