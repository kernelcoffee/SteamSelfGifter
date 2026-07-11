"""Giveaway scanner worker.

Scans SteamGifts for new giveaways and syncs them to the local database.
Exposed as the manual ``/scan`` and ``/scan/quick`` triggers; the scheduled
cycle performs the same scan step inline via ``automation_cycle``.
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from core.events import event_manager
from workers.context import automation_context

logger = structlog.get_logger()


def _skipped_scan() -> dict[str, Any]:
    """Uniform 'not authenticated' scan result."""
    return {
        "new": 0,
        "updated": 0,
        "pages_scanned": 0,
        "scan_time": 0,
        "skipped": True,
        "reason": "not_authenticated",
    }


async def scan_giveaways() -> dict[str, Any]:
    """
    Scan SteamGifts for giveaways and sync to database (manual trigger).

    Scans ``max_scan_pages`` pages and emits a ``scan_completed`` event.

    Returns:
        Dictionary with scan results (new/updated/pages_scanned/scan_time).
    """
    start_time = datetime.now(UTC)

    logger.info("giveaway_scan_started")

    async with automation_context() as ctx:
        if not ctx.authenticated:
            logger.warning("giveaway_scan_skipped", reason="not_authenticated")
            return _skipped_scan()

        max_pages = ctx.settings.max_scan_pages or 3

        try:
            await ctx.notification_service.log_scan_start(pages=max_pages)

            new_count, updated_count = await ctx.giveaway_service.sync_giveaways(
                pages=max_pages
            )

            scan_time = (datetime.now(UTC) - start_time).total_seconds()
            results = {
                "new": new_count,
                "updated": updated_count,
                "pages_scanned": max_pages,
                "scan_time": round(scan_time, 2),
                "skipped": False,
            }

            await ctx.notification_service.log_scan_complete(
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

            await event_manager.broadcast_event("scan_completed", results)
            return results

        except Exception as e:
            logger.error(
                "giveaway_scan_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            await event_manager.broadcast_event("scan_failed", {"error": str(e)})
            raise


async def quick_scan() -> dict[str, Any]:
    """
    Perform a quick scan (single page only).

    Useful for immediate updates without full scan overhead.

    Returns:
        Dictionary with scan results.
    """
    logger.info("quick_scan_started")

    async with automation_context() as ctx:
        if not ctx.authenticated:
            return _skipped_scan()

        start_time = datetime.now(UTC)
        new_count, updated_count = await ctx.giveaway_service.sync_giveaways(pages=1)
        scan_time = (datetime.now(UTC) - start_time).total_seconds()

        return {
            "new": new_count,
            "updated": updated_count,
            "pages_scanned": 1,
            "scan_time": round(scan_time, 2),
            "skipped": False,
        }
