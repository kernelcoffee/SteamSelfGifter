"""Unit tests for the win-check worker job."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from core.exceptions import SteamGiftsSessionExpiredError
from core.time import utcnow
from services.scheduler_service import WIN_CHECK_JOB_ID, SchedulerService
from tests.conftest import patch_automation_context
from workers.scheduler import SchedulerManager
from workers.win_check import run_win_check

pytestmark = pytest.mark.usefixtures("uncached_win_check_logger")


def _settings(phpsessid: str | None = "test_session") -> MagicMock:
    """Settings mock; a falsy PHPSESSID makes the patched context unauthenticated."""
    settings = MagicMock()
    settings.phpsessid = phpsessid
    return settings


def _events(logs: list[dict[str, object]]) -> list[str]:
    """Event names of the captured log entries, in order."""
    return [str(entry["event"]) for entry in logs]


class _ContextFailingOnEntry:
    """Stand-in for automation_context whose client start fails on entry."""

    async def __aenter__(self) -> MagicMock:
        raise SteamGiftsSessionExpiredError("Failed to fetch homepage: 503", code="SG_004")

    async def __aexit__(self, *exc_info: object) -> None:
        raise AssertionError("a context that failed to open is never exited")


class _ContextFailingOnExit:
    """Stand-in for automation_context that opens but fails to close its clients."""

    def __init__(self, ctx: MagicMock) -> None:
        self.ctx = ctx

    async def __aenter__(self) -> MagicMock:
        return self.ctx

    async def __aexit__(self, *exc_info: object) -> None:
        raise RuntimeError("client close failed")


@pytest.mark.asyncio
async def test_run_win_check_syncs_and_reschedules_with_fresh_context() -> None:
    """The job syncs one won page and reschedules through the services of the
    context it opened itself."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.return_value = 1
    scheduler_service = AsyncMock()

    patcher, _ = patch_automation_context(
        "workers.win_check",
        _settings(),
        giveaway_service=giveaway_service,
        scheduler_service=scheduler_service,
    )
    with patcher, capture_logs() as logs:
        await run_win_check()

    giveaway_service.sync_wins.assert_awaited_once_with(pages=1)
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert {"event": "wins_detected", "new_wins": 1, "log_level": "info"} in logs


@pytest.mark.asyncio
async def test_run_win_check_logs_no_wins_when_none_found() -> None:
    """No new win: nothing is reported as detected, the next check is still scheduled."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.return_value = 0
    scheduler_service = AsyncMock()

    patcher, _ = patch_automation_context(
        "workers.win_check",
        _settings(),
        giveaway_service=giveaway_service,
        scheduler_service=scheduler_service,
    )
    with patcher, capture_logs() as logs:
        await run_win_check()

    assert "wins_detected" not in _events(logs)
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_win_check_skips_when_not_authenticated() -> None:
    """Without a PHPSESSID the job logs the skip, raises nothing and schedules nothing."""
    patcher, ctx = patch_automation_context("workers.win_check", _settings(phpsessid=None))
    with patcher, capture_logs() as logs:
        await run_win_check()

    assert ctx.giveaway_service is None
    assert ctx.scheduler_service is None
    assert logs == [{"event": "win_check_skipped", "reason": "not_authenticated", "log_level": "info"}]


@pytest.mark.asyncio
async def test_run_win_check_reschedules_after_sync_failure() -> None:
    """A failed sync is logged and the next check is still scheduled; nothing
    escapes to APScheduler."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()

    patcher, _ = patch_automation_context(
        "workers.win_check",
        _settings(),
        giveaway_service=giveaway_service,
        scheduler_service=scheduler_service,
    )
    with patcher, capture_logs() as logs:
        await run_win_check()

    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert {"event": "win_check_failed", "error": "session expired", "log_level": "error"} in logs


@pytest.mark.asyncio
async def test_run_win_check_logs_reschedule_failure() -> None:
    """A reschedule failure after a successful sync is logged, not raised."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.return_value = 0
    scheduler_service = AsyncMock()
    scheduler_service.schedule_next_win_check.side_effect = RuntimeError("scheduler down")

    patcher, _ = patch_automation_context(
        "workers.win_check",
        _settings(),
        giveaway_service=giveaway_service,
        scheduler_service=scheduler_service,
    )
    with patcher, capture_logs() as logs:
        await run_win_check()

    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert {"event": "win_check_reschedule_failed", "error": "scheduler down", "log_level": "error"} in logs
    assert "win_check_failed" not in _events(logs)


@pytest.mark.asyncio
async def test_win_check_job_runs_after_scheduling_session_closed(async_engine: AsyncEngine) -> None:
    """The job registered by a (request-scoped) SchedulerService still runs
    after that service's session has closed, using the job's own context."""
    manager = SchedulerManager()
    manager.start()
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        with patch("services.scheduler_service.scheduler_manager", manager):
            async with session_maker() as request_session:
                request_service = SchedulerService(request_session)
                await request_service.update_win_check_for_new_entry(utcnow() + timedelta(days=1))

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None

            giveaway_service = AsyncMock()
            giveaway_service.sync_wins.return_value = 0
            scheduler_service = AsyncMock()
            patcher, _ = patch_automation_context(
                "workers.win_check",
                _settings(),
                giveaway_service=giveaway_service,
                scheduler_service=scheduler_service,
            )
            with patcher:
                await job.func(*job.args, **job.kwargs)
    finally:
        manager.stop(wait=False)

    giveaway_service.sync_wins.assert_awaited_once_with(pages=1)
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_win_check_reschedules_when_context_fails_to_open(async_engine: AsyncEngine) -> None:
    """A failure opening automation_context is logged as win_check_failed and
    the next check is scheduled from a session of the job's own."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    scheduler_service = AsyncMock()

    with (
        patch("workers.win_check.automation_context", _ContextFailingOnEntry),
        patch("workers.win_check.AsyncSessionLocal", session_maker),
        patch("workers.win_check.SchedulerService", return_value=scheduler_service) as service_class,
        capture_logs() as logs,
    ):
        await run_win_check()

    [(args, _)] = service_class.call_args_list
    assert isinstance(args[0], AsyncSession)
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert logs == [{"event": "win_check_failed", "error": "Failed to fetch homepage: 503", "log_level": "error"}]


@pytest.mark.asyncio
async def test_run_win_check_logs_reschedule_failure_after_context_failure(async_engine: AsyncEngine) -> None:
    """When the context cannot open and the fallback reschedule fails too, both
    failures are logged and nothing escapes to APScheduler."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    scheduler_service = AsyncMock()
    scheduler_service.schedule_next_win_check.side_effect = RuntimeError("scheduler down")

    with (
        patch("workers.win_check.automation_context", _ContextFailingOnEntry),
        patch("workers.win_check.AsyncSessionLocal", session_maker),
        patch("workers.win_check.SchedulerService", return_value=scheduler_service),
        capture_logs() as logs,
    ):
        await run_win_check()

    assert _events(logs) == ["win_check_failed", "win_check_reschedule_failed"]
    assert logs[1]["error"] == "scheduler down"


@pytest.mark.asyncio
async def test_run_win_check_propagates_context_exit_error_after_rescheduling() -> None:
    """An error raised while the context closes is not swallowed: it reaches
    APScheduler, and only after the sync and the reschedule have run."""
    ctx = MagicMock()
    ctx.authenticated = True
    ctx.giveaway_service = AsyncMock()
    ctx.giveaway_service.sync_wins.return_value = 0
    ctx.scheduler_service = AsyncMock()

    with (
        patch("workers.win_check.automation_context", lambda: _ContextFailingOnExit(ctx)),
        pytest.raises(RuntimeError, match="client close failed"),
    ):
        await run_win_check()

    ctx.giveaway_service.sync_wins.assert_awaited_once_with(pages=1)
    ctx.scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_win_check_logs_both_failures_when_sync_and_reschedule_fail() -> None:
    """A failed sync followed by a failed reschedule logs both failures, in
    that order, and nothing escapes to APScheduler."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()
    scheduler_service.schedule_next_win_check.side_effect = RuntimeError("scheduler down")

    patcher, _ = patch_automation_context(
        "workers.win_check",
        _settings(),
        giveaway_service=giveaway_service,
        scheduler_service=scheduler_service,
    )
    with patcher, capture_logs() as logs:
        await run_win_check()

    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert logs == [
        {"event": "win_check_failed", "error": "session expired", "log_level": "error"},
        {"event": "win_check_reschedule_failed", "error": "scheduler down", "log_level": "error"},
    ]
