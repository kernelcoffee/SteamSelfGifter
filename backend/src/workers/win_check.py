"""Win-check worker.

The ``win_check`` APScheduler job registered by
``SchedulerService._schedule_win_check_job``. It fires shortly after the
soonest-expiring entered giveaway ends, syncs the won page and schedules the
next check.

The job may fire long after the API request or worker cycle that scheduled it
has closed its session and HTTP clients, so it opens its own
``automation_context`` every time instead of holding on to the scheduler's
services.

A failure is surfaced the way scan and automation-cycle failures are: an
``error`` row in the activity log and a ``win_check_failed`` WebSocket event.
"""

from collections.abc import Iterable
from contextlib import AsyncExitStack

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from core.events import event_manager
from db.session import AsyncSessionLocal
from repositories.settings import SettingsRepository
from services.notification_service import NotificationService
from services.scheduler_service import SchedulerService
from workers.context import automation_context

REDACTED = "[redacted]"

logger = structlog.get_logger()


async def run_win_check() -> None:
    """
    Sync wins from SteamGifts and schedule the next win check.

    Skipped (nothing synced, nothing scheduled) when no PHPSESSID is
    configured. A failure to open the context (for example the SteamGifts
    homepage is down when the client starts) or to sync (the won page cannot
    be fetched, or the sync cannot commit) is logged as ``win_check_failed``,
    reported to the activity log and the WebSocket (see ``_report_failure``)
    and the next check is still scheduled; a failed reschedule is logged as
    ``win_check_reschedule_failed``. None of these reaches APScheduler. An
    error raised while the context closes its clients and session on exit is
    not caught: it propagates and APScheduler logs it as a job error once the
    steps above have run.

    Example:
        >>> scheduler_manager.add_date_job(
        ...     func=run_win_check, job_id="win_check", run_date=run_at
        ... )
    """
    async with AsyncExitStack() as stack:
        try:
            ctx = await stack.enter_async_context(automation_context())
        except Exception as e:
            await _recover_from_own_session(e)
            return

        if not ctx.authenticated:
            logger.info("win_check_skipped", reason="not_authenticated")
            return

        # authenticated=True guarantees the full service stack was built.
        assert ctx.giveaway_service and ctx.scheduler_service

        try:
            new_wins = await ctx.giveaway_service.sync_wins(pages=1)
        except Exception as e:
            await _report_failure(e, ctx.session)
        else:
            if new_wins > 0:
                logger.info("wins_detected", new_wins=new_wins)

        try:
            await ctx.scheduler_service.schedule_next_win_check()
        except Exception as e:
            logger.error("win_check_reschedule_failed", error=str(e))


async def _recover_from_own_session(error: Exception) -> None:
    """
    Report the failure and schedule the next win check from one short session.

    Used when ``automation_context`` could not be opened, so the failure is
    still visible and the chain of win checks does not stop on a SteamGifts
    outage. Starts no HTTP client; the next run is bounded by the next entered
    giveaway's end time. A reschedule failure is logged, not raised.

    Args:
        error: The exception raised while opening the context
    """
    try:
        async with AsyncSessionLocal() as session:
            await _report_failure(error, session)
            await SchedulerService(session).schedule_next_win_check()
    except Exception as e:
        logger.error("win_check_reschedule_failed", error=str(e))


async def _report_failure(error: Exception, session: AsyncSession) -> None:
    """
    Log a failed win check, record it in the activity log and broadcast it.

    Rolls the session back first (a failed commit leaves it unusable) and
    reads the stored PHPSESSID and XSRF value to redact them from the
    message. The redacted message is then logged as ``win_check_failed``,
    written as an ``error`` activity-log row through ``NotificationService``
    and broadcast as ``win_check_failed`` with ``{"error": message}``. When
    the stored secrets cannot be read, the message is only the exception's
    class name. Each step that fails is logged as ``win_check_report_failed``;
    nothing is raised, so the caller still reschedules.

    Args:
        error: The exception that made the win check fail
        session: The session to write the activity-log row with
    """
    message = type(error).__name__
    try:
        await session.rollback()
        settings = await SettingsRepository(session).get_settings()
        message = _redact(str(error), (settings.phpsessid, settings.xsrf_token))
    except Exception as e:
        logger.error("win_check_report_failed", step="redact", error=str(e))

    logger.error("win_check_failed", error=message)

    try:
        await NotificationService(session).log_error(error_type="win_check", message=message)
    except Exception as e:
        logger.error("win_check_report_failed", step="activity_log", error=str(e))

    try:
        await event_manager.broadcast_event("win_check_failed", {"error": message})
    except Exception as e:
        logger.error("win_check_report_failed", step="broadcast", error=str(e))


def _redact(message: str, secrets: Iterable[str | None]) -> str:
    """
    Replace every occurrence of each non-empty secret in ``message``.

    Args:
        message: Text that may quote a secret
        secrets: Secret values; None and empty strings are ignored

    Returns:
        The message with each secret replaced by ``REDACTED``
    """
    for secret in secrets:
        if secret:
            message = message.replace(secret, REDACTED)
    return message
