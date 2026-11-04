"""Giveaway processor worker.

Enters the candidates the auto-join engine (services.eligibility) selects for
the cycle, within the points budget and the per-cycle cap.

``_process_entries`` is the single entry loop, shared by the scheduled
``automation_cycle`` and the manual ``/process`` trigger (``process_giveaways``).
When safety checks are enabled, each entry is vetted inline (check → hide if
unsafe → enter) so unsafe giveaways are never entered.
"""

import asyncio
import functools
import random
from datetime import UTC, datetime
from typing import Any

import structlog

from core.events import event_manager
from core.time import utcnow
from models.giveaway import Giveaway
from models.settings import Settings
from services.eligibility import (
    BUDGET_FLOOR,
    ELIGIBLE,
    CycleBudget,
    Detail,
    InvalidPolicyError,
    gate_of,
    policy_from_settings,
)
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

    Shared by :func:`process_giveaways` and ``automation_cycle``. Builds the
    auto-join policy, fetches the points balance, decides and records the
    whole candidate pool (``decide_cycle``, even when nothing will be
    entered, so stored decisions never go stale), then walks the enter
    candidates in entry order, entering them one at a time with human-like
    delays, and records what it did for each. When
    ``settings.safety_check_enabled`` is set, each entry is vetted inline and
    unsafe giveaways are hidden instead of entered.

    Fails closed: an invalid stored priority or genre list, or an unavailable
    points balance, enters nothing. Enforces the points budget and the cap
    through :class:`services.eligibility.CycleBudget` with the balance
    actually spent: nothing is entered below ``autojoin_start_at``, no entry
    may draw the running balance below ``autojoin_stop_at``, at most
    ``max_entries_per_cycle`` attempts are made, and a failed attempt spends
    nothing, so a later candidate it would have priced out is still tried.

    Args:
        giveaway_service: GiveawayService instance
        notification_service: NotificationService instance
        settings: Settings object with autojoin configuration

    Returns:
        Dictionary with entry results
    """
    start_time = datetime.now(UTC)

    try:
        policy = policy_from_settings(settings)
    except InvalidPolicyError as e:
        reason = f"invalid_{e.setting}"
        logger.error("entry_processing_skipped", reason=reason, error=str(e))
        await notification_service.log_error(error_type="entry", message=str(e))
        return _skipped_stats(reason)

    start_at = policy.start_at
    points = await giveaway_service.fetch_points()

    # Decide and record the whole pool first, whatever the balance.
    result = await giveaway_service.decide_cycle(policy, points)

    if points is None:
        logger.warning("entry_processing_skipped", reason="points_unavailable")
        await notification_service.log_error(
            error_type="entry",
            message="Points balance unavailable; no entries this cycle",
        )
        skip_stats = _skipped_stats("points_unavailable")
        skip_stats["decisions"] = result.counts
        skip_stats["candidates"] = result.total
        return skip_stats

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
            details={"points": points, "start_at": start_at, "decisions": result.counts},
        )
        skip_stats = _skipped_stats("points_below_start_threshold")
        skip_stats["points_available"] = points
        skip_stats["decisions"] = result.counts
        skip_stats["candidates"] = result.total
        return skip_stats

    candidates = result.candidates

    stats: dict[str, Any] = {
        "eligible": len(candidates),
        "entered": 0,
        "failed": 0,
        "points_spent": 0,
        "points_available": points,
        "skipped_budget": 0,
        "skipped": False,
        "decisions": result.counts,
        "candidates": result.total,
    }

    if not candidates:
        logger.info("no_eligible_giveaways")
        await notification_service.log_activity(
            level="info",
            event_type="entry",
            message="Processing completed: No eligible giveaways found",
            details={"decisions": result.counts},
        )
        return stats

    # Enter with inline safety check when enabled, otherwise enter directly.
    safety_enabled = getattr(settings, "safety_check_enabled", False)
    enter = (
        functools.partial(
            giveaway_service.enter_giveaway_with_safety_check,
            hide_on_steamgifts=policy.auto_hide_unsafe,
        )
        if safety_enabled
        else giveaway_service.enter_giveaway
    )

    # Process giveaways with delays
    delay_min = settings.entry_delay_min or 5
    delay_max = settings.entry_delay_max or 15

    # The budget follows the balance actually spent: a failed attempt spends
    # nothing, so a cheaper candidate the plan priced out is still tried.
    budget = CycleBudget.for_cycle(points, policy)
    # What the loop did for each candidate, in order; recorded after the loop.
    outcomes: list[tuple[Giveaway, str, Detail]] = []

    for candidate in candidates:
        giveaway = candidate.giveaway

        # Per-cycle cap, then budget floor: entering must not take the
        # balance below stop_at. A cheaper giveaway later in the list may
        # still fit, so skip, don't stop.
        skip = budget.skip(giveaway.price)
        if skip is not None:
            code, detail = skip
            outcomes.append((giveaway, code, detail))
            if code == BUDGET_FLOOR:
                stats["skipped_budget"] += 1
            logger.debug("entry_skipped", code=giveaway.code, reason=code, **detail)
            continue

        # Apply delay between entry attempts (except before the first one)
        if budget.attempts > 0:
            delay = random.uniform(delay_min, delay_max)
            logger.debug("entry_delay", delay=delay)
            await asyncio.sleep(delay)

        if giveaway.is_wishlist:
            entry_type = "wishlist"
        elif giveaway.is_dlc:
            entry_type = "dlc"
        else:
            entry_type = "auto"

        # Points this attempt spent; a failed or crashed attempt spends none.
        spent = 0
        # What to record for this attempt: eligible unless it entered nothing
        # because a gate now stops it (see below).
        outcome: tuple[str, Detail] = (ELIGIBLE, candidate.decision.detail)
        try:
            entry = await enter(giveaway.code, entry_type=entry_type)

            if entry:
                spent = entry.points_spent
                stats["entered"] += 1
                stats["points_spent"] += entry.points_spent

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
                # None means the entry was skipped (e.g. unsafe) or failed;
                # the Entry row records the reason — no activity log needed.
                stats["failed"] += 1

                logger.warning(
                    "giveaway_entry_failed",
                    code=giveaway.code,
                    reason="entry_returned_none",
                )

                # The inline safety check may just have flagged the giveaway
                # (is_safe False, or hidden): record that gate, not eligible.
                gate = gate_of(giveaway, policy, utcnow())
                if gate is not None:
                    outcome = gate

        except Exception as e:
            stats["failed"] += 1

            # Unexpected exceptions are real system events (unlike ordinary
            # entry failures, which live as Entry rows in History).
            await notification_service.log_error(
                error_type="entry",
                message=f"Entering {giveaway.game_name} ({giveaway.code}) crashed: {e}",
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

        budget.attempt(spent)
        outcomes.append((giveaway, *outcome))

    await giveaway_service.record_outcomes(outcomes)
    stats["decisions"] = result.counts_after(outcomes)

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
