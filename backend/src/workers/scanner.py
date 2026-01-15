"""Giveaway scanner worker.

Background job that scans SteamGifts for new giveaways and syncs them
to the local database.
"""

from datetime import datetime, UTC
from typing import Dict, Any

import structlog

from db.session import AsyncSessionLocal
from services.giveaway_service import GiveawayService
from services.game_service import GameService
from services.settings_service import SettingsService
from services.notification_service import NotificationService
from utils.steamgifts_client import SteamGiftsClient
from utils.steam_client import SteamClient
from core.events import event_manager

logger = structlog.get_logger()


async def scan_giveaways() -> Dict[str, Any]:
    """
    Scan SteamGifts for giveaways and sync to database.

    This is the main scanner job function that:
    1. Checks if scanning is enabled in settings
    2. Scans multiple pages from SteamGifts
    3. Syncs new/updated giveaways to database
    4. Emits events for real-time updates

    Returns:
        Dictionary with scan results:
            - new: Number of new giveaways found
            - updated: Number of existing giveaways updated
            - pages_scanned: Number of pages scanned
            - scan_time: Time taken in seconds

    Example:
        >>> results = await scan_giveaways()
        >>> print(f"Found {results['new']} new giveaways")
    """
    start_time = datetime.now(UTC)

    logger.info("giveaway_scan_started")

    async with AsyncSessionLocal() as session:
        # Check settings
        settings_service = SettingsService(session)
        settings = await settings_service.get_settings()

        # Skip if not authenticated
        if not settings.phpsessid:
            logger.warning("giveaway_scan_skipped", reason="not_authenticated")
            return {
                "new": 0,
                "updated": 0,
                "pages_scanned": 0,
                "scan_time": 0,
                "skipped": True,
                "reason": "not_authenticated",
            }

        # Get scan configuration
        max_pages = settings.max_scan_pages or 3

        # Create clients
        sg_client = SteamGiftsClient(
            phpsessid=settings.phpsessid,
            user_agent=settings.user_agent,
        )
        await sg_client.start()

        steam_client = SteamClient()
        await steam_client.start()

        game_service = GameService(session, steam_client)
        giveaway_service = GiveawayService(
            session=session,
            steamgifts_client=sg_client,
            game_service=game_service,
        )
        notification_service = NotificationService(session=session)

        try:
            # Log scan start
            await notification_service.log_scan_start(pages=max_pages)
            # Perform sync
            new_count, updated_count = await giveaway_service.sync_giveaways(
                pages=max_pages
            )

            # Calculate time taken
            end_time = datetime.now(UTC)
            scan_time = (end_time - start_time).total_seconds()

            results = {
                "new": new_count,
                "updated": updated_count,
                "pages_scanned": max_pages,
                "scan_time": round(scan_time, 2),
                "skipped": False,
            }

            # Log scan completion
            await notification_service.log_scan_complete(
                new_count=new_count,
                updated_count=updated_count
            )

            logger.info(
                "giveaway_scan_completed",
                new=new_count,
                updated=updated_count,
                pages=max_pages,
                scan_time=scan_time,
            )

            # Emit event for real-time updates
            await event_manager.broadcast_event("scan_completed", results)

            return results

        except Exception as e:
            logger.error(
                "giveaway_scan_failed",
                error=str(e),
                error_type=type(e).__name__,
            )

            # Emit error event
            await event_manager.broadcast_event("scan_failed", {"error": str(e)})

            raise

        finally:
            await sg_client.close()
            await steam_client.close()


async def quick_scan() -> Dict[str, Any]:
    """
    Perform a quick scan (single page only).

    Useful for immediate updates without full scan overhead.

    Returns:
        Dictionary with scan results

    Example:
        >>> results = await quick_scan()
    """
    logger.info("quick_scan_started")

    async with AsyncSessionLocal() as session:
        settings_service = SettingsService(session)
        settings = await settings_service.get_settings()

        if not settings.phpsessid:
            return {
                "new": 0,
                "updated": 0,
                "pages_scanned": 0,
                "scan_time": 0,
                "skipped": True,
                "reason": "not_authenticated",
            }

        sg_client = SteamGiftsClient(
            phpsessid=settings.phpsessid,
            user_agent=settings.user_agent,
        )
        await sg_client.start()

        steam_client = SteamClient()
        await steam_client.start()

        game_service = GameService(session, steam_client)
        giveaway_service = GiveawayService(
            session=session,
            steamgifts_client=sg_client,
            game_service=game_service,
        )

        try:
            start_time = datetime.now(UTC)
            new_count, updated_count = await giveaway_service.sync_giveaways(pages=1)
            scan_time = (datetime.now(UTC) - start_time).total_seconds()

            return {
                "new": new_count,
                "updated": updated_count,
                "pages_scanned": 1,
                "scan_time": round(scan_time, 2),
                "skipped": False,
            }
        finally:
            await sg_client.close()
            await steam_client.close()
