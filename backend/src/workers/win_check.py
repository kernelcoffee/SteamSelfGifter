"""Win-check worker.

The ``win_check`` APScheduler job registered by
``SchedulerService._schedule_win_check_job``. It fires shortly after the
soonest-expiring entered giveaway ends, syncs the won page and schedules the
next check.

The job may fire long after the API request or worker cycle that scheduled it
has closed its session and HTTP clients, so it opens its own
``automation_context`` every time instead of holding on to the scheduler's
services.
"""

from contextlib import AsyncExitStack

import structlog

from db.session import AsyncSessionLocal
from services.scheduler_service import SchedulerService
from workers.context import automation_context

logger = structlog.get_logger()


async def run_win_check() -> None:
    """
    Sync wins from SteamGifts and schedule the next win check.

    Skipped (nothing synced, nothing scheduled) when no PHPSESSID is
    configured. A failure to open the context (for example the SteamGifts
    homepage is down when the client starts) or to sync is logged as
    ``win_check_failed`` and the next check is still scheduled; a failed
    reschedule is logged as ``win_check_reschedule_failed``. None of these
    reaches APScheduler. An error raised while the context closes its clients
    and session on exit is not caught: it propagates and APScheduler logs it
    as a job error once the steps above have run.

    Example:
        >>> scheduler_manager.add_date_job(
        ...     func=run_win_check, job_id="win_check", run_date=run_at
        ... )
    """
    async with AsyncExitStack() as stack:
        try:
            ctx = await stack.enter_async_context(automation_context())
        except Exception as e:
            logger.error("win_check_failed", error=str(e))
            await _reschedule_from_own_session()
            return

        if not ctx.authenticated:
            logger.info("win_check_skipped", reason="not_authenticated")
            return

        # authenticated=True guarantees the full service stack was built.
        assert ctx.giveaway_service and ctx.scheduler_service

        try:
            new_wins = await ctx.giveaway_service.sync_wins(pages=1)
        except Exception as e:
            logger.error("win_check_failed", error=str(e))
        else:
            if new_wins > 0:
                logger.info("wins_detected", new_wins=new_wins)

        try:
            await ctx.scheduler_service.schedule_next_win_check()
        except Exception as e:
            logger.error("win_check_reschedule_failed", error=str(e))


async def _reschedule_from_own_session() -> None:
    """
    Schedule the next win check from a short session of its own.

    Used when ``automation_context`` could not be opened, so the chain of win
    checks does not stop on a SteamGifts outage. Starts no HTTP client; the
    next run is bounded by the next entered giveaway's end time. A failure is
    logged, not raised.
    """
    try:
        async with AsyncSessionLocal() as session:
            await SchedulerService(session).schedule_next_win_check()
    except Exception as e:
        logger.error("win_check_reschedule_failed", error=str(e))
