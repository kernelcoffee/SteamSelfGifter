"""Giveaway processor worker.

Enters eligible giveaways automatically based on the configured criteria.

``_process_entries`` is the single entry loop, shared by the scheduled
``automation_cycle`` and the manual ``/process`` trigger (``process_giveaways``).
When safety checks are enabled, each entry is vetted inline (check → hide if
unsafe → enter) so unsafe giveaways are never entered.
"""

import asyncio
import random
from datetime import UTC, datetime
from typing import Any

import structlog

from core.events import event_manager
from models.settings import Settings
from services.eligibility import EligibilityCriteria
from services.giveaway_service import GiveawayService
from services.notification_service import NotificationService
from workers.context import automation_context

logger = structlog.get_logger()


async def process_giveaways() -> dict[str, Any]:
    """
    Process eligible giveaways and enter them automatically (manual trigger).

    Thin wrapper around :func:`_process_entries`: opens the shared automation
    context, validates that we're authenticated and autojoin is enabled, then
    delegates to the shared entry loop.

    Returns:
        Dictionary with processing results (eligible/entered/failed/points_spent).
    """
    logger.info("giveaway_processing_started")

    async with automation_context() as ctx:
        if not ctx.authenticated:
            logger.warning("giveaway_processing_skipped", reason="not_authenticated")
            return _skipped_stats("not_authenticated")

        if not ctx.settings.autojoin_enabled:
            logger.info("giveaway_processing_skipped", reason="autojoin_disabled")
            return _skipped_stats("autojoin_disabled")

        # authenticated=True guarantees the full service stack was built.
        assert ctx.giveaway_service and ctx.notification_service and ctx.scheduler_service

        stats = await _process_entries(
            giveaway_service=ctx.giveaway_service,
            notification_service=ctx.notification_service,
            settings=ctx.settings,
        )

        # Schedule a win check if we entered anything (mirrors automation_cycle).
        if stats.get("entered", 0) > 0:
            await ctx.scheduler_service.schedule_next_win_check()

        await event_manager.broadcast_event("processing_completed", stats)
        return stats


def _skipped_stats(reason: str) -> dict[str, Any]:
    """Build a uniform 'skipped' result for the processor."""
    return {
        "eligible": 0,
        "entered": 0,
        "failed": 0,
        "points_spent": 0,
        "skipped": True,
        "reason": reason,
    }


async def _process_entries(
    giveaway_service: GiveawayService,
    notification_service: NotificationService,
    settings: Settings,
) -> dict[str, Any]:
    """
    Internal entry processing logic.

    Shared by :func:`process_giveaways` and ``automation_cycle``. Fetches
    eligible giveaways and enters them with human-like delays. When
    ``settings.safety_check_enabled`` is set, each entry is vetted inline and
    unsafe giveaways are hidden instead of entered.

    Enforces the points budget: the cycle only spends once the balance has
    accumulated past ``autojoin_start_at``, and no entry may draw it below
    ``autojoin_stop_at``. If the balance can't be fetched it reads as 0 and
    the cycle is skipped rather than spending blindly.

    Args:
        giveaway_service: GiveawayService instance
        notification_service: NotificationService instance
        settings: Settings object with autojoin configuration

    Returns:
        Dictionary with entry results
    """
    start_time = datetime.now(UTC)

    # Points budget: spend only once the balance has accumulated past
    # autojoin_start_at, and never draw it below autojoin_stop_at.
    start_at = settings.autojoin_start_at or 0
    stop_at = settings.autojoin_stop_at or 0
    points = await giveaway_service.get_current_points()

    if points < start_at:
        logger.info(
            "entry_processing_skipped",
            reason="points_below_start_threshold",
            points=points,
            start_at=start_at,
        )
        await notification_service.log_activity(
            level="info",
            event_type="entry",
            message=f"Accumulating points: {points}P is below the {start_at}P start threshold",
        )
        stats = _skipped_stats("points_below_start_threshold")
        stats["points_available"] = points
        return stats

    # Evaluate the candidate pool: this both selects the eligible giveaways and
    # records a per-giveaway eligibility reason for the ones that didn't qualify.
    max_entries = settings.max_entries_per_cycle or 10
    criteria = EligibilityCriteria(
        min_price=settings.autojoin_min_price or 0,
        max_price=None,
        min_score=settings.autojoin_min_score,
        min_reviews=settings.autojoin_min_reviews,
        max_game_age=settings.autojoin_max_game_age,
        wishlist_priority=bool(settings.wishlist_priority_enabled),
        dlc_priority=bool(settings.dlc_priority_enabled),
    )
    eligible = await giveaway_service.evaluate_and_get_eligible(criteria, limit=max_entries)

    stats: dict[str, Any] = {
        "eligible": len(eligible),
        "entered": 0,
        "failed": 0,
        "points_spent": 0,
        "points_available": points,
        "skipped_budget": 0,
        "skipped": False,
    }

    if not eligible:
        logger.info("no_eligible_giveaways")
        await notification_service.log_activity(
            level="info",
            event_type="entry",
            message="Processing completed: No eligible giveaways found"
        )
        return stats

    # Enter with inline safety check when enabled, otherwise enter directly.
    safety_enabled = getattr(settings, "safety_check_enabled", False)
    enter = (
        giveaway_service.enter_giveaway_with_safety_check
        if safety_enabled
        else giveaway_service.enter_giveaway
    )

    # Process giveaways with delays
    delay_min = settings.entry_delay_min or 5
    delay_max = settings.entry_delay_max or 15

    for giveaway in eligible:
        # Budget floor: entering must not take the balance below stop_at.
        # Eligible is ordered by price descending, so a cheaper giveaway
        # later in the list may still fit — skip, don't stop.
        if points - giveaway.price < stop_at:
            stats["skipped_budget"] += 1
            logger.debug(
                "entry_skipped_budget",
                code=giveaway.code,
                price=giveaway.price,
                points=points,
                stop_at=stop_at,
            )
            continue

        # Apply delay between entry attempts (except before the first one)
        if stats["entered"] + stats["failed"] > 0:
            delay = random.uniform(delay_min, delay_max)
            logger.debug("entry_delay", delay=delay)
            await asyncio.sleep(delay)

        if giveaway.is_wishlist:
            entry_type = "wishlist"
        elif giveaway.is_dlc:
            entry_type = "dlc"
        else:
            entry_type = "auto"

        try:
            entry = await enter(giveaway.code, entry_type=entry_type)

            if entry:
                stats["entered"] += 1
                stats["points_spent"] += entry.points_spent
                points -= entry.points_spent

                await notification_service.log_entry_success(
                    giveaway_code=giveaway.code,
                    game_name=giveaway.game_name,
                    points=entry.points_spent
                )

                await event_manager.broadcast_event(
                    "entry_success",
                    {
                        "giveaway_code": giveaway.code,
                        "game_name": giveaway.game_name,
                        "points_spent": entry.points_spent,
                    }
                )

                logger.info(
                    "giveaway_entered",
                    code=giveaway.code,
                    points_spent=entry.points_spent,
                )
            else:
                # None means the entry was skipped (e.g. unsafe) or failed.
                stats["failed"] += 1

                await notification_service.log_entry_failure(
                    giveaway_code=giveaway.code,
                    game_name=giveaway.game_name,
                    reason="Entry returned none"
                )

                logger.warning(
                    "giveaway_entry_failed",
                    code=giveaway.code,
                    reason="entry_returned_none",
                )

        except Exception as e:
            stats["failed"] += 1

            await notification_service.log_entry_failure(
                giveaway_code=giveaway.code,
                game_name=giveaway.game_name,
                reason=str(e)
            )

            logger.error(
                "giveaway_entry_error",
                code=giveaway.code,
                error=str(e),
            )

            await event_manager.broadcast_event(
                "entry_failed",
                {
                    "giveaway_code": giveaway.code,
                    "error": str(e),
                }
            )

    # Calculate processing time
    end_time = datetime.now(UTC)
    stats["processing_time"] = round((end_time - start_time).total_seconds(), 2)

    # Log completion
    await notification_service.log_activity(
        level="info",
        event_type="entry",
        message=(
            f"Processing completed: {stats['entered']} entered, "
            f"{stats['failed']} failed, {stats['points_spent']}P spent"
        ),
        details=stats
    )

    logger.info("entry_processing_completed", **stats)

    return stats


async def enter_single_giveaway(giveaway_code: str) -> dict[str, Any]:
    """
    Enter a single giveaway by code (manual, user-initiated entry).

    Args:
        giveaway_code: The giveaway code to enter

    Returns:
        Dictionary with entry result (success/points_spent/error).
    """
    logger.info("single_entry_started", code=giveaway_code)

    async with automation_context() as ctx:
        if not ctx.authenticated:
            return {"success": False, "points_spent": 0, "error": "Not authenticated"}

        assert ctx.giveaway_service is not None

        try:
            entry = await ctx.giveaway_service.enter_giveaway(
                giveaway_code,
                entry_type="manual"
            )

            if entry:
                logger.info(
                    "single_entry_success",
                    code=giveaway_code,
                    points_spent=entry.points_spent,
                )
                return {
                    "success": True,
                    "points_spent": entry.points_spent,
                    "error": None,
                }

            return {"success": False, "points_spent": 0, "error": "Entry failed"}

        except Exception as e:
            logger.error("single_entry_failed", code=giveaway_code, error=str(e))
            return {"success": False, "points_spent": 0, "error": str(e)}
