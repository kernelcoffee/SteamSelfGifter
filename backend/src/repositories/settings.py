"""Settings repository with singleton pattern accessor methods.

This module provides a specialized repository for the Settings model, which
follows a singleton pattern (always id=1). It wraps the BaseRepository with
convenience methods for getting and updating the single settings record.
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from models.settings import Settings
from repositories.base import BaseRepository


class SettingsRepository(BaseRepository[Settings]):
    """
    Repository for Settings model with singleton pattern support.

    This repository extends BaseRepository to provide specialized methods
    for working with the Settings singleton (id=1). It ensures there's
    always exactly one settings record in the database.

    Design Notes:
        - Settings table follows singleton pattern (id=1)
        - get_settings() automatically creates record if missing
        - update_settings() ensures only the singleton is modified
        - No delete operation (settings must always exist)

    Usage:
        >>> async with AsyncSessionLocal() as session:
        ...     repo = SettingsRepository(session)
        ...     settings = await repo.get_settings()
        ...     await repo.update_settings(autojoin_enabled=True)
        ...     await session.commit()
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize SettingsRepository with database session.

        Args:
            session: The async database session

        Example:
            >>> repo = SettingsRepository(session)
        """
        super().__init__(Settings, session)

    async def get_settings(self) -> Settings:
        """
        Get the singleton settings record, creating it if it doesn't exist.

        This method ensures that the settings record always exists. If no
        settings are found (first run), a new record with default values
        is created automatically.

        Returns:
            The Settings instance (id=1)

        Example:
            >>> settings = await repo.get_settings()
            >>> print(settings.autojoin_enabled)
            False  # default value
        """
        settings = await self.get_by_id(1)

        if settings is None:
            # First run - create settings with default values
            settings = await self.create(id=1)
            await self.session.flush()

        return settings

    async def update_settings(self, **kwargs) -> Settings:
        """
        Update the singleton settings record.

        Updates the settings with the provided field values. This method
        ensures only the singleton record (id=1) is updated.

        Args:
            **kwargs: Field values to update

        Returns:
            The updated Settings instance

        Example:
            >>> settings = await repo.update_settings(
            ...     autojoin_enabled=True,
            ...     autojoin_start_at=400,
            ...     scan_interval_minutes=45
            ... )
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        # Ensure settings exist first
        await self.get_settings()

        # Update the singleton record
        settings = await self.update(1, **kwargs)

        # This should never be None since we just ensured it exists
        if settings is None:
            raise RuntimeError("Settings record disappeared unexpectedly")

        return settings

    async def get_phpsessid(self) -> Optional[str]:
        """
        Get the SteamGifts session ID.

        Convenience method to retrieve just the PHPSESSID cookie value
        without fetching the entire settings record.

        Returns:
            The PHPSESSID value, or None if not set

        Example:
            >>> phpsessid = await repo.get_phpsessid()
            >>> if phpsessid:
            ...     print("Authenticated")
        """
        settings = await self.get_settings()
        return settings.phpsessid

    async def set_phpsessid(self, phpsessid: str) -> Settings:
        """
        Update the SteamGifts session ID.

        Convenience method to update just the PHPSESSID cookie value.

        Args:
            phpsessid: The new PHPSESSID cookie value

        Returns:
            The updated Settings instance

        Example:
            >>> settings = await repo.set_phpsessid("new_session_id_here")
            >>> await session.commit()

        Note:
            This method does NOT commit the transaction. The caller must
            call session.commit() to persist changes to the database.
        """
        return await self.update_settings(phpsessid=phpsessid)

    async def is_authenticated(self) -> bool:
        """
        Check if SteamGifts credentials are configured.

        Returns:
            True if PHPSESSID is set, False otherwise

        Example:
            >>> if await repo.is_authenticated():
            ...     print("Can make SteamGifts API calls")
        """
        phpsessid = await self.get_phpsessid()
        return phpsessid is not None and phpsessid.strip() != ""

    async def get_autojoin_config(self) -> dict:
        """
        Get autojoin configuration as a dictionary.

        Convenience method to retrieve all autojoin-related settings
        in a single dictionary for easy access.

        Returns:
            Dictionary with autojoin configuration fields

        Example:
            >>> config = await repo.get_autojoin_config()
            >>> if config['enabled']:
            ...     print(f"Autojoin starts at {config['start_at']} points")
        """
        settings = await self.get_settings()
        return {
            "enabled": settings.autojoin_enabled,
            "start_at": settings.autojoin_start_at,
            "stop_at": settings.autojoin_stop_at,
            "min_price": settings.autojoin_min_price,
            "min_score": settings.autojoin_min_score,
            "min_reviews": settings.autojoin_min_reviews,
        }

    async def get_scheduler_config(self) -> dict:
        """
        Get scheduler configuration as a dictionary.

        Convenience method to retrieve all scheduler-related settings
        in a single dictionary for easy access.

        Returns:
            Dictionary with scheduler configuration fields

        Example:
            >>> config = await repo.get_scheduler_config()
            >>> print(f"Scan interval: {config['scan_interval_minutes']} minutes")
        """
        settings = await self.get_settings()
        return {
            "automation_enabled": settings.automation_enabled,
            "scan_interval_minutes": settings.scan_interval_minutes,
            "max_entries_per_cycle": settings.max_entries_per_cycle,
            "entry_delay_min": settings.entry_delay_min,
            "entry_delay_max": settings.entry_delay_max,
            "max_scan_pages": settings.max_scan_pages,
        }
