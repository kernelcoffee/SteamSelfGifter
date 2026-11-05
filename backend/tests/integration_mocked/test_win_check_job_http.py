"""The win_check job against a mocked SteamGifts over real httpx plumbing.

Reproduces the PR #79 failure mode: the job is scheduled by a request-scoped
SchedulerService whose session and HTTP clients are gone by the time the job
fires. The job must open its own context (fresh session, freshly started
SteamGifts client) instead of raising "Client session not started".
"""

from datetime import timedelta
from functools import partial
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from core.events import event_manager
from core.time import to_naive_utc, utcnow
from models.activity_log import ActivityLog
from models.giveaway import Giveaway
from services.scheduler_service import WIN_CHECK_JOB_ID, SchedulerService
from services.settings_service import SettingsService
from tests.integration_mocked.conftest import RoutedTransport
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient
from workers.scheduler import SchedulerManager

pytestmark = [pytest.mark.asyncio, pytest.mark.usefixtures("uncached_win_check_logger")]


async def test_job_fired_after_request_ended_uses_fresh_clients(
    async_engine: AsyncEngine,
    transport: RoutedTransport,
    wishlist_html: str,
    empty_search_html: str,
) -> None:
    """A win_check scheduled during a request syncs wins on a newly started
    client and reschedules from a new session after that request closed."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)

    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="PEND1", url="/giveaway/PEND1/", game_name="Pending", price=10,
                             end_time=end_time, is_entered=True))
        await session.commit()

    # The SteamGifts homepage (XSRF on start) and an empty won page.
    transport.add("GET", "/", httpx.Response(200, text=wishlist_html))
    transport.add("GET", "/giveaways/won", httpx.Response(200, text=empty_search_html))
    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            # The request: schedule the check, then its session ends.
            async with session_maker() as request_session:
                await SchedulerService(request_session).update_win_check_for_new_entry(end_time)

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None
            manager.remove_job(WIN_CHECK_JOB_ID)

            with capture_logs() as logs:
                await job.func(*job.args, **job.kwargs)

            rescheduled = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    assert [(r.method, r.url.path) for r in transport.requests] == [("GET", "/"), ("GET", "/giveaways/won")]
    assert all(r.headers["Cookie"] == "PHPSESSID=test_session" for r in transport.requests)
    assert steam_transport.requests == []
    assert not any(entry["log_level"] == "error" for entry in logs)
    assert rescheduled is not None
    assert to_naive_utc(rescheduled.next_run_time) == end_time + timedelta(minutes=5)


async def test_job_survives_and_reschedules_when_client_start_fails(
    async_engine: AsyncEngine,
    transport: RoutedTransport,
    no_sleep: object,
) -> None:
    """When the SteamGifts homepage is down as the job fires, starting the
    client inside automation_context fails: the error is logged, written to
    the activity log and broadcast without the PHPSESSID, nothing escapes to
    APScheduler, and the next win check is still scheduled from a session of
    the job's own."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)

    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="PEND2", url="/giveaway/PEND2/", game_name="Pending", price=10,
                             end_time=end_time, is_entered=True))
        await session.commit()

    # Homepage unavailable when the job fires: start() cannot read the XSRF token.
    transport.add("GET", "/", httpx.Response(503, text="Service Unavailable"))
    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.win_check.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            async with session_maker() as request_session:
                await SchedulerService(request_session).update_win_check_for_new_entry(end_time)

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None
            manager.remove_job(WIN_CHECK_JOB_ID)

            with (
                capture_logs() as logs,
                patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            ):
                await job.func(*job.args, **job.kwargs)  # must not raise

            rescheduled = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    failures = [entry for entry in logs if entry["event"] == "win_check_failed"]
    assert len(failures) == 1
    assert "test_session" not in str(failures[0])

    async with session_maker() as session:
        rows = (await session.scalars(select(ActivityLog))).all()
    assert [(row.level, row.event_type) for row in rows] == [("error", "error")]
    assert rows[0].message == f"[win_check] {failures[0]['error']}"
    assert "test_session" not in f"{rows[0].message} {rows[0].details}"
    broadcast.assert_awaited_once_with("win_check_failed", {"error": failures[0]["error"]})
    assert "test_session" not in str(broadcast.await_args_list)
    assert "win_check_reschedule_failed" not in [entry["event"] for entry in logs]
    assert {r.url.path for r in transport.requests} == {"/"}
    assert steam_transport.requests == []
    assert rescheduled is not None
    assert to_naive_utc(rescheduled.next_run_time) == end_time + timedelta(minutes=5)


async def test_won_page_failure_is_recorded_and_broadcast(
    async_engine: AsyncEngine,
    transport: RoutedTransport,
    wishlist_html: str,
    no_sleep: object,
) -> None:
    """When the homepage loads but /giveaways/won keeps answering 503, the
    sync raises: the job writes one error activity-log row and broadcasts
    win_check_failed without the PHPSESSID, raises nothing and still
    schedules the next check."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)

    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="PEND3", url="/giveaway/PEND3/", game_name="Pending", price=10,
                             end_time=end_time, is_entered=True))
        await session.commit()

    transport.add("GET", "/", httpx.Response(200, text=wishlist_html))
    transport.add("GET", "/giveaways/won", httpx.Response(503, text="Service Unavailable"))
    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            async with session_maker() as request_session:
                await SchedulerService(request_session).update_win_check_for_new_entry(end_time)

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None
            manager.remove_job(WIN_CHECK_JOB_ID)

            with (
                capture_logs() as logs,
                patch.object(event_manager, "broadcast_event", new_callable=AsyncMock) as broadcast,
            ):
                await job.func(*job.args, **job.kwargs)  # must not raise

            rescheduled = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    async with session_maker() as session:
        rows = (await session.scalars(select(ActivityLog))).all()
    assert [(row.level, row.event_type, row.message) for row in rows] == [
        ("error", "error", "[win_check] Failed to fetch won giveaways: 503")
    ]
    broadcast.assert_awaited_once_with("win_check_failed", {"error": "Failed to fetch won giveaways: 503"})
    assert {"event": "win_check_failed", "error": "Failed to fetch won giveaways: 503", "log_level": "error"} in logs
    assert "test_session" not in f"{rows[0].message} {rows[0].details} {broadcast.await_args_list} {logs}"
    assert "win_check_reschedule_failed" not in [entry["event"] for entry in logs]
    assert transport.requests[0].url.path == "/"
    assert {r.url.path for r in transport.requests[1:]} == {"/giveaways/won"}
    assert steam_transport.requests == []
    assert rescheduled is not None
    assert to_naive_utc(rescheduled.next_run_time) == end_time + timedelta(minutes=5)


def _won_page(code: str, game_name: str) -> str:
    """A /giveaways/won page with one row for the given giveaway."""
    return f"""
    <html><body>
    <div class="table__row-inner-wrap">
        <div class="table__column--width-fill">
            <p><a class="table__column__heading" href="/giveaway/{code}/game">{game_name}</a></p>
            <p>Ended <span data-timestamp="1704067200">1 year</span> ago</p>
        </div>
    </div>
    </body></html>
    """


async def test_job_records_win_and_moves_check_to_next_pending_giveaway(
    async_engine: AsyncEngine,
    transport: RoutedTransport,
    wishlist_html: str,
) -> None:
    """A job fired after the scheduling request ended persists the win it
    found (committed from its own session) and moves the next check to the
    next pending entered giveaway."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    ended = utcnow() - timedelta(minutes=10)
    next_end = utcnow() + timedelta(days=2)

    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add_all([
            Giveaway(code="WON01", url="/giveaway/WON01/", game_name="Won Game", price=10,
                     end_time=ended, is_entered=True),
            Giveaway(code="NEXT1", url="/giveaway/NEXT1/", game_name="Next Game", price=10,
                     end_time=next_end, is_entered=True),
        ])
        await session.commit()

    transport.add("GET", "/", httpx.Response(200, text=wishlist_html))
    transport.add("GET", "/giveaways/won", httpx.Response(200, text=_won_page("WON01", "Won Game")))
    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            # The request entering NEXT1 schedules the check; its session then ends.
            async with session_maker() as request_session:
                await SchedulerService(request_session).update_win_check_for_new_entry(next_end)

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None
            manager.remove_job(WIN_CHECK_JOB_ID)

            with capture_logs() as logs:
                await job.func(*job.args, **job.kwargs)

            rescheduled = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    async with session_maker() as session:
        won = await session.scalar(select(Giveaway).where(Giveaway.code == "WON01"))
        pending = await session.scalar(select(Giveaway).where(Giveaway.code == "NEXT1"))
    assert won is not None and won.is_won is True and won.won_at is not None
    assert pending is not None and pending.is_won is False

    assert {"event": "wins_detected", "new_wins": 1, "log_level": "info"} in logs
    assert not any(entry["log_level"] == "error" for entry in logs), logs
    assert "test_session" not in str(logs)
    assert rescheduled is not None
    assert to_naive_utc(rescheduled.next_run_time) == next_end + timedelta(minutes=5)


async def test_job_without_phpsessid_sends_nothing_and_schedules_nothing(
    async_engine: AsyncEngine,
    transport: RoutedTransport,
) -> None:
    """With the PHPSESSID cleared after the check was scheduled, the job
    (through the real automation_context) sends no request to SteamGifts or
    Steam, logs the skip, raises nothing and leaves no win_check job behind."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)

    async with session_maker() as session:
        session.add(Giveaway(code="PEND4", url="/giveaway/PEND4/", game_name="Pending", price=10,
                             end_time=end_time, is_entered=True))
        await session.commit()

    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.win_check.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            async with session_maker() as request_session:
                await SchedulerService(request_session).update_win_check_for_new_entry(end_time)

            job = manager.get_job(WIN_CHECK_JOB_ID)
            assert job is not None
            manager.remove_job(WIN_CHECK_JOB_ID)

            with capture_logs() as logs:
                await job.func(*job.args, **job.kwargs)

            leftover = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    assert transport.requests == []
    assert steam_transport.requests == []
    assert {"event": "win_check_skipped", "reason": "not_authenticated", "log_level": "info"} in logs
    assert not any(entry["log_level"] == "error" for entry in logs), logs
    assert leftover is None
