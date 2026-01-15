"""FastAPI dependency injection for database sessions and services.

This module provides dependency functions for FastAPI endpoints,
enabling clean dependency injection of database sessions and service layers.
"""

from typing import Annotated
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from db.session import get_db
from services.settings_service import SettingsService
from services.notification_service import NotificationService
from services.game_service import GameService
from services.giveaway_service import GiveawayService
from services.scheduler_service import SchedulerService
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient


# Database session dependency
# This is re-exported from db.session for convenience
async def get_database() -> AsyncSession:
    """
    Get database session dependency.

    Re-exports get_db from db.session for API layer use.

    Yields:
        AsyncSession: Database session

    Example:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_database)):
            ...
    """
    async for session in get_db():
        yield session


# Type aliases for cleaner endpoint signatures
DatabaseDep = Annotated[AsyncSession, Depends(get_database)]


# Service dependencies
def get_settings_service(db: DatabaseDep) -> SettingsService:
    """
    Get SettingsService dependency.

    Args:
        db: Database session from dependency injection

    Returns:
        SettingsService instance

    Example:
        @router.get("/settings")
        async def get_settings(
            settings_service: SettingsService = Depends(get_settings_service)
        ):
            return await settings_service.get_settings()
    """
    return SettingsService(db)


def get_notification_service(db: DatabaseDep) -> NotificationService:
    """
    Get NotificationService dependency.

    Args:
        db: Database session from dependency injection

    Returns:
        NotificationService instance

    Example:
        @router.get("/logs")
        async def get_logs(
            notification_service: NotificationService = Depends(get_notification_service)
        ):
            return await notification_service.get_recent_logs()
    """
    return NotificationService(db)


# Type aliases for service dependencies (for cleaner endpoint signatures)
SettingsServiceDep = Annotated[SettingsService, Depends(get_settings_service)]
NotificationServiceDep = Annotated[NotificationService, Depends(get_notification_service)]


async def get_game_service(db: DatabaseDep) -> GameService:
    """
    Get GameService dependency.

    Creates a GameService with SteamClient for Steam API access.

    Args:
        db: Database session from dependency injection

    Returns:
        GameService instance

    Example:
        @router.get("/games/{app_id}")
        async def get_game(
            app_id: int,
            game_service: GameService = Depends(get_game_service)
        ):
            return await game_service.get_or_fetch_game(app_id)
    """
    steam_client = SteamClient()
    await steam_client.start()
    return GameService(db, steam_client)


async def get_giveaway_service(db: DatabaseDep) -> GiveawayService:
    """
    Get GiveawayService dependency.

    Creates a GiveawayService with SteamGiftsClient and GameService.
    Note: Requires PHPSESSID to be configured in settings for entry operations.

    Args:
        db: Database session from dependency injection

    Returns:
        GiveawayService instance

    Example:
        @router.get("/giveaways")
        async def list_giveaways(
            giveaway_service: GiveawayService = Depends(get_giveaway_service)
        ):
            return await giveaway_service.get_active_giveaways()
    """
    # Get settings for credentials
    settings_service = SettingsService(db)
    settings = await settings_service.get_settings()

    # Create SteamGifts client (may not be authenticated)
    sg_client = SteamGiftsClient(
        phpsessid=settings.phpsessid or "",
        user_agent=settings.user_agent,
    )
    await sg_client.start()

    # Create Steam client for game data
    steam_client = SteamClient()
    await steam_client.start()

    # Create game service
    game_service = GameService(db, steam_client)

    return GiveawayService(db, sg_client, game_service)


async def get_scheduler_service(db: DatabaseDep) -> SchedulerService:
    """
    Get SchedulerService dependency.

    Args:
        db: Database session from dependency injection

    Returns:
        SchedulerService instance

    Example:
        @router.get("/scheduler/stats")
        async def get_stats(
            scheduler_service: SchedulerService = Depends(get_scheduler_service)
        ):
            return await scheduler_service.get_scheduler_stats()
    """
    # SchedulerService needs GiveawayService, so get that first
    giveaway_service = await get_giveaway_service(db)
    return SchedulerService(db, giveaway_service)


# Type aliases for new service dependencies
GameServiceDep = Annotated[GameService, Depends(get_game_service)]
GiveawayServiceDep = Annotated[GiveawayService, Depends(get_giveaway_service)]
SchedulerServiceDep = Annotated[SchedulerService, Depends(get_scheduler_service)]


# Example usage in routers:
"""
from api.dependencies import DatabaseDep, SettingsServiceDep

@router.get("/settings")
async def get_settings(settings_service: SettingsServiceDep):
    '''Get application settings.'''
    settings = await settings_service.get_settings()
    return create_success_response(data=settings)

# Or using the underlying dependency function:
@router.get("/settings")
async def get_settings(
    settings_service: SettingsService = Depends(get_settings_service)
):
    '''Get application settings.'''
    settings = await settings_service.get_settings()
    return create_success_response(data=settings)

# Direct database access if needed:
@router.get("/custom")
async def custom_endpoint(db: DatabaseDep):
    '''Custom endpoint with direct database access.'''
    result = await db.execute(select(Model))
    return result.scalars().all()
"""
