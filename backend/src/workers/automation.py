"""Automation cycle worker.

Single unified job that performs all automated tasks in sequence:
1. Scan regular giveaways
2. Scan wishlist giveaways
3. Scan DLC giveaways
4. Sync wins
5. Sync entered giveaways
6. Process eligible giveaways (enter them)

This is the engine driven both by the scheduler (interval job) and by the
manual ``/run`` trigger. It shares its bootstrap with the other workers via
``automation_context`` and its entry loop with ``/process`` via
``_process_entries``.
"""

from datetime import UTC, datetime
from typing import Any

import structlog

from core.events import event_manager
from workers.context import automation_context
from workers.processor import _process_entries

logger = structlog.get_logger()


async def automation_cycle() -> dict[str, Any]:
    """
    Run a complete automation cycle.

    Runs all tasks in sequence: scan regular + wishlist + DLC giveaways,
    sync wins, sync entered giveaways, then enter eligible giveaways.

    Returns:
        Dictionary with per-step results and total ``cycle_time``.

    Example:
        >>> results = await automation_cycle()
        >>> print(f"Cycle complete: {results['entries']['entered']} entries")
    """
    start_time = datetime.now(UTC)

    logger.info("automation_cycle_started")

    results: dict[str, Any] = {
        "scan": {"new": 0, "updated": 0, "skipped": False},
        "wishlist": {"new": 0, "updated": 0, "skipped": False},
        "wins": {"new_wins": 0, "skipped": False},
        "entries": {"eligible": 0, "entered": 0, "failed": 0, "points_spent": 0, "skipped": False},
        "cycle_time": 0,
        "skipped": False,
    }

    async with automation_context() as ctx:
        # Skip if not authenticated
        if not ctx.authenticated:
            logger.warning("automation_cycle_skipped", reason="not_authenticated")
            results["skipped"] = True
            results["reason"] = "not_authenticated"
            return results

        settings = ctx.settings
        giveaway_service = ctx.giveaway_service
        notification_service = ctx.notification_service
        scheduler_service = ctx.scheduler_service
        # authenticated=True guarantees the full service stack was built.
        assert giveaway_service and notification_service and scheduler_service

        try:
            # === STEP 1: Scan regular giveaways ===
            logger.info("automation_step", step="scan_giveaways")
            max_pages = settings.max_scan_pages or 3

            try:
                new_count, updated_count = await giveaway_service.sync_giveaways(pages=max_pages)
                results["scan"] = {
                    "new": new_count,
                    "updated": updated_count,
                    "pages": max_pages,
                    "skipped": False,
                }
                await notification_service.log_scan_complete(
                    new_count=new_count,
                    updated_count=updated_count
                )
            except Exception as e:
                logger.error("scan_giveaways_failed", error=str(e))
                results["scan"]["error"] = str(e)

            # === STEP 2: Scan wishlist giveaways ===
            logger.info("automation_step", step="scan_wishlist")

            try:
                # Same page cap as the regular scan; the sync stops early at
                # the end of the list, so small wishlists cost one request.
                wishlist_new, wishlist_updated = await giveaway_service.sync_giveaways(
                    pages=max_pages,
                    giveaway_type="wishlist"
                )
                results["wishlist"] = {
                    "new": wishlist_new,
                    "updated": wishlist_updated,
                    "skipped": False,
                }
            except Exception as e:
                logger.error("scan_wishlist_failed", error=str(e))
                results["wishlist"]["error"] = str(e)

            # === STEP 2.5: Scan DLC giveaways ===
            # Always scanned, like the wishlist: the is_dlc flags it maintains
            # feed both the DLC badge and the optional autojoin priority.
            logger.info("automation_step", step="scan_dlc")
            results["dlc"] = {"new": 0, "updated": 0, "skipped": False}

            try:
                dlc_new, dlc_updated = await giveaway_service.sync_giveaways(
                    pages=max_pages,
                    dlc_only=True
                )
                results["dlc"] = {
                    "new": dlc_new,
                    "updated": dlc_updated,
                    "skipped": False,
                }
                logger.info("scan_dlc_completed", new=dlc_new, updated=dlc_updated)
            except Exception as e:
                logger.error("scan_dlc_failed", error=str(e))
                results["dlc"]["error"] = str(e)

            # === STEP 3: Sync wins ===
            logger.info("automation_step", step="sync_wins")

            try:
                new_wins = await giveaway_service.sync_wins(pages=1)
                results["wins"] = {
                    "new_wins": new_wins,
                    "skipped": False,
                }
                if new_wins > 0:
                    logger.info("new_wins_detected", count=new_wins)
                    await notification_service.log_activity(
                        level="info",
                        event_type="win",
                        message=f"Detected {new_wins} new win(s)!",
                    )
            except Exception as e:
                logger.error("sync_wins_failed", error=str(e))
                results["wins"]["error"] = str(e)

            # === STEP 3.5: Sync entered giveaways ===
            logger.info("automation_step", step="sync_entered")
            results["entered_sync"] = {"synced": 0, "skipped": False}

            try:
                synced = await giveaway_service.sync_entered_giveaways(pages=1)
                results["entered_sync"] = {
                    "synced": synced,
                    "skipped": False,
                }
                if synced > 0:
                    logger.info("entered_giveaways_synced", count=synced)
            except Exception as e:
                logger.error("sync_entered_failed", error=str(e))
                results["entered_sync"]["error"] = str(e)

            # === STEP 4: Process entries ===
            logger.info("automation_step", step="process_entries")

            # Only process if autojoin is enabled
            if not settings.autojoin_enabled:
                results["entries"]["skipped"] = True
                results["entries"]["reason"] = "autojoin_disabled"
            else:
                try:
                    entry_results = await _process_entries(
                        giveaway_service=giveaway_service,
                        notification_service=notification_service,
                        settings=settings,
                    )
                    results["entries"] = entry_results

                    # Schedule win check if we entered any giveaways
                    if entry_results.get("entered", 0) > 0:
                        await scheduler_service.schedule_next_win_check()

                except Exception as e:
                    logger.error("process_entries_failed", error=str(e))
                    results["entries"]["error"] = str(e)

            # Calculate total cycle time
            end_time = datetime.now(UTC)
            results["cycle_time"] = round((end_time - start_time).total_seconds(), 2)

            logger.info(
                "automation_cycle_completed",
                scan_new=results["scan"]["new"],
                scan_updated=results["scan"]["updated"],
                wishlist_new=results["wishlist"]["new"],
                new_wins=results["wins"]["new_wins"],
                entries_entered=results["entries"].get("entered", 0),
                cycle_time=results["cycle_time"],
            )

            # Emit completion event
            await event_manager.broadcast_event("automation_cycle_completed", results)

            return results

        except Exception as e:
            logger.error(
                "automation_cycle_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            await event_manager.broadcast_event("automation_cycle_failed", {"error": str(e)})
            raise


async def sync_wins_only() -> dict[str, Any]:
    """
    Sync wins only (manual trigger).

    Returns:
        Dictionary with win sync results.
    """
    logger.info("sync_wins_started")

    async with automation_context() as ctx:
        if not ctx.authenticated:
            return {"new_wins": 0, "skipped": True, "reason": "not_authenticated"}

        assert ctx.giveaway_service is not None
        new_wins = await ctx.giveaway_service.sync_wins(pages=1)

        logger.info("sync_wins_completed", new_wins=new_wins)

        return {
            "new_wins": new_wins,
            "skipped": False,
        }
