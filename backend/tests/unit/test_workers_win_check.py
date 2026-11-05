"""Unit tests for the win-check worker job."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from core.events import event_manager
from core.exceptions import SteamGiftsSessionExpiredError
from core.time import utcnow
from models.activity_log import ActivityLog
from repositories.settings import SettingsRepository
from services.notification_service import NotificationService
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


@pytest.fixture
def session_maker(async_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory on the test engine, for the job's own sessions."""
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


async def _activity_rows(session_maker: async_sessionmaker[AsyncSession]) -> list[tuple[str, str, str]]:
    """(level, event_type, message) of every activity-log row, read from a new session."""
    async with session_maker() as session:
        rows = (await session.scalars(select(ActivityLog).order_by(ActivityLog.id))).all()
    return [(row.level, row.event_type, row.message) for row in rows]


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
async def test_sync_failure_is_logged_to_activity_log_and_broadcast(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A failed sync writes an error row to the activity log through the
    context's session, broadcasts win_check_failed and still schedules the
    next check; nothing escapes to APScheduler."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch("workers.win_check.NotificationService", wraps=NotificationService) as notification_class,
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    [(args, _)] = notification_class.call_args_list
    assert args[0] is session
    broadcast.assert_awaited_once_with("win_check_failed", {"error": "session expired"})
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert logs == [{"event": "win_check_failed", "error": "session expired", "log_level": "error"}]
    assert await _activity_rows(session_maker) == [("error", "error", "[win_check] session expired")]


@pytest.mark.asyncio
async def test_sync_failure_after_failed_flush_is_still_recorded(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When sync_wins leaves the context's session needing a rollback (a
    failed flush or commit), the failure is still written to the activity log
    and the next check is still scheduled."""
    scheduler_service = AsyncMock()

    async with session_maker() as session:

        async def failing_sync(pages: int) -> int:
            session.add(ActivityLog(level="info", event_type="scan", message=None))
            await session.flush()
            return 0

        giveaway_service = AsyncMock()
        giveaway_service.sync_wins.side_effect = failing_sync
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    assert _events(logs) == ["win_check_failed"]
    [row] = await _activity_rows(session_maker)
    assert row[:2] == ("error", "error")
    assert row[2].startswith("[win_check] (sqlite3.IntegrityError) NOT NULL constraint failed")
    broadcast.assert_awaited_once()
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_failure_message_never_carries_session_secrets(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """An error message quoting the stored PHPSESSID or XSRF value reaches
    neither the win_check_failed log line, the activity-log row nor the
    broadcast payload."""
    phpsessid = "secret-phpsessid-value"
    xsrf = "secret-xsrf-value"
    async with session_maker() as session:
        await SettingsRepository(session).update_settings(phpsessid=phpsessid, xsrf_token=xsrf)
        await session.commit()

    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = RuntimeError(f"rejected cookie {phpsessid} with token {xsrf}")
    scheduler_service = AsyncMock()

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(phpsessid),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    assert logs == [
        {"event": "win_check_failed", "error": "rejected cookie [redacted] with token [redacted]", "log_level": "error"}
    ]
    rows = await _activity_rows(session_maker)
    assert rows == [("error", "error", "[win_check] rejected cookie [redacted] with token [redacted]")]
    broadcast.assert_awaited_once_with("win_check_failed", {"error": "rejected cookie [redacted] with token [redacted]"})
    for secret in (phpsessid, xsrf):
        assert secret not in str(rows)
        assert secret not in str(broadcast.await_args_list)
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_unreadable_secrets_report_only_the_error_class(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When the stored secrets cannot be read the message cannot be redacted:
    only the exception's class name is logged, written to the activity log
    and broadcast, and the next check is still scheduled."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = RuntimeError("rejected cookie secret-phpsessid-value")
    scheduler_service = AsyncMock()
    repository = MagicMock()
    repository.get_settings = AsyncMock(side_effect=RuntimeError("database is locked"))

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch("workers.win_check.SettingsRepository", return_value=repository),
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    broadcast.assert_awaited_once_with("win_check_failed", {"error": "RuntimeError"})
    assert logs == [
        {"event": "win_check_report_failed", "step": "redact", "error": "database is locked", "log_level": "error"},
        {"event": "win_check_failed", "error": "RuntimeError", "log_level": "error"},
    ]
    assert await _activity_rows(session_maker) == [("error", "error", "[win_check] RuntimeError")]
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_report_failure_errors_never_escape(session_maker: async_sessionmaker[AsyncSession]) -> None:
    """When the activity-log write and the broadcast both raise, both are
    logged as win_check_report_failed, the broadcast is still attempted and
    the job still reschedules."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()
    notification_service = MagicMock()
    notification_service.log_error = AsyncMock(side_effect=RuntimeError("disk full"))

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch("workers.win_check.NotificationService", return_value=notification_service),
            patch.object(
                event_manager, "broadcast_event", new_callable=AsyncMock, side_effect=RuntimeError("socket gone")
            ) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    notification_service.log_error.assert_awaited_once_with(error_type="win_check", message="session expired")
    broadcast.assert_awaited_once_with("win_check_failed", {"error": "session expired"})
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    assert logs == [
        {"event": "win_check_failed", "error": "session expired", "log_level": "error"},
        {"event": "win_check_report_failed", "step": "activity_log", "error": "disk full", "log_level": "error"},
        {"event": "win_check_report_failed", "step": "broadcast", "error": "socket gone", "log_level": "error"},
    ]


@pytest.mark.asyncio
async def test_broadcast_failure_keeps_activity_row_and_reschedule(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A broadcast that raises is logged; the activity-log row is already
    written and the next check is still scheduled."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock, side_effect=RuntimeError("boom")),
            capture_logs() as logs,
        ):
            await run_win_check()

    assert _events(logs) == ["win_check_failed", "win_check_report_failed"]
    assert logs[1]["step"] == "broadcast"
    assert await _activity_rows(session_maker) == [("error", "error", "[win_check] session expired")]
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


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
async def test_context_open_failure_is_reported_from_own_session(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A failure opening automation_context is logged as win_check_failed,
    written to the activity log and broadcast, and the next check is
    scheduled, all from one session of the job's own."""
    scheduler_service = AsyncMock()

    with (
        patch("workers.win_check.automation_context", _ContextFailingOnEntry),
        patch("workers.win_check.AsyncSessionLocal", session_maker),
        patch("workers.win_check.NotificationService", wraps=NotificationService) as notification_class,
        patch("workers.win_check.SchedulerService", return_value=scheduler_service) as service_class,
        patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
        capture_logs() as logs,
    ):
        await run_win_check()

    [(scheduler_args, _)] = service_class.call_args_list
    [(notification_args, _)] = notification_class.call_args_list
    assert isinstance(scheduler_args[0], AsyncSession)
    assert notification_args[0] is scheduler_args[0]
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
    broadcast.assert_awaited_once_with("win_check_failed", {"error": "Failed to fetch homepage: 503"})
    assert logs == [{"event": "win_check_failed", "error": "Failed to fetch homepage: 503", "log_level": "error"}]
    assert await _activity_rows(session_maker) == [("error", "error", "[win_check] Failed to fetch homepage: 503")]


class _ContextFailingWithSecrets:
    """Stand-in for automation_context whose entry error quotes the session."""

    def __init__(self, message: str) -> None:
        self.message = message

    async def __aenter__(self) -> MagicMock:
        raise RuntimeError(self.message)

    async def __aexit__(self, *exc_info: object) -> None:
        raise AssertionError("a context that failed to open is never exited")


@pytest.mark.asyncio
async def test_context_open_failure_never_logs_session_secrets(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When the context-open error quotes the stored PHPSESSID or XSRF value,
    the win_check_failed log line, the activity-log row and the broadcast all
    carry the redacted message, read from the job's own session."""
    phpsessid = "secret-phpsessid-value"
    xsrf = "secret-xsrf-value"
    async with session_maker() as session:
        await SettingsRepository(session).update_settings(phpsessid=phpsessid, xsrf_token=xsrf)
        await session.commit()
    scheduler_service = AsyncMock()
    redacted = "rejected cookie [redacted] with token [redacted]"

    with (
        patch(
            "workers.win_check.automation_context",
            lambda: _ContextFailingWithSecrets(f"rejected cookie {phpsessid} with token {xsrf}"),
        ),
        patch("workers.win_check.AsyncSessionLocal", session_maker),
        patch("workers.win_check.SchedulerService", return_value=scheduler_service),
        patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
        capture_logs() as logs,
    ):
        await run_win_check()

    assert logs == [{"event": "win_check_failed", "error": redacted, "log_level": "error"}]
    assert await _activity_rows(session_maker) == [("error", "error", f"[win_check] {redacted}")]
    broadcast.assert_awaited_once_with("win_check_failed", {"error": redacted})
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_run_win_check_logs_reschedule_failure_after_context_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """When the context cannot open and the fallback reschedule fails too, both
    failures are logged and nothing escapes to APScheduler."""
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
async def test_run_win_check_logs_both_failures_when_sync_and_reschedule_fail(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A failed sync followed by a failed reschedule logs both failures, in
    that order, and nothing escapes to APScheduler."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.side_effect = SteamGiftsSessionExpiredError("session expired", code="SG_004")
    scheduler_service = AsyncMock()
    scheduler_service.schedule_next_win_check.side_effect = RuntimeError("scheduler down")

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
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


@pytest.mark.asyncio
async def test_won_page_failure_from_real_sync_wins_is_reported(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A failed win check is visible when the homepage loads but
    /giveaways/won fails (503): the real sync_wins raises, so the job writes
    an error activity-log row, broadcasts win_check_failed and still
    schedules the next check."""
    from core.exceptions import SteamGiftsError
    from services.giveaway_service import GiveawayService

    sg_client = MagicMock()
    sg_client.get_won_giveaways = AsyncMock(
        side_effect=SteamGiftsError("Failed to fetch won giveaways: 503", code="SG_002")
    )
    scheduler_service = AsyncMock()

    async with session_maker() as session:
        giveaway_service = GiveawayService(session=session, steamgifts_client=sg_client, game_service=MagicMock())
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with patcher, patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast:
            await run_win_check()

    rows = await _activity_rows(session_maker)
    assert [(level, message.startswith("[win_check]")) for level, _, message in rows] == [("error", True)]
    broadcast.assert_awaited_once()
    assert broadcast.await_args.args[0] == "win_check_failed"
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_successful_win_check_records_no_failure(
    session_maker: async_sessionmaker[AsyncSession],
) -> None:
    """A win check that syncs fine writes no activity-log row, broadcasts no
    win_check_failed and logs no error: the dashboard is not told the bot is
    failing when it is not."""
    giveaway_service = AsyncMock()
    giveaway_service.sync_wins.return_value = 2
    scheduler_service = AsyncMock()

    async with session_maker() as session:
        patcher, _ = patch_automation_context(
            "workers.win_check",
            _settings(),
            session=session,
            giveaway_service=giveaway_service,
            scheduler_service=scheduler_service,
        )
        with (
            patcher,
            patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            capture_logs() as logs,
        ):
            await run_win_check()

    broadcast.assert_not_awaited()
    assert await _activity_rows(session_maker) == []
    assert not any(entry["log_level"] == "error" for entry in logs), logs
    scheduler_service.schedule_next_win_check.assert_awaited_once_with()
