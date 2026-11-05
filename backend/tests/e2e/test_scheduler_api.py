"""End-to-end tests for scheduler API endpoints.

These drive the real FastAPI app + router + APScheduler against the in-memory
test database. Two pieces of wiring make that possible (see ``_wire_scheduler_e2e``):

- Worker jobs open their own DB session via ``workers.context.AsyncSessionLocal``
  (outside FastAPI's dependency injection), so it's patched onto the test engine.
- The router and service bind the module-level ``scheduler_manager`` at import,
  so each test gets a fresh, isolated ``SchedulerManager`` patched into both.
"""

from datetime import timedelta
from functools import partial
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from core.time import utcnow
from models.giveaway import Giveaway
from services.scheduler_service import WIN_CHECK_JOB_ID, SchedulerService
from services.settings_service import SettingsService
from tests.integration_mocked.conftest import RoutedTransport
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient
from workers.scheduler import SchedulerManager

FIXTURES = Path(__file__).parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def _wire_scheduler_e2e(async_engine):
    """Point worker DB sessions at the test engine and isolate the scheduler.

    ``async_engine`` is the same function-scoped in-memory engine the
    ``test_client`` fixture uses, so worker sessions share the test database.
    """
    worker_session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=True,
    )

    fresh_manager = SchedulerManager()

    with patch("workers.context.AsyncSessionLocal", worker_session_factory), \
         patch("api.routers.scheduler.scheduler_manager", fresh_manager), \
         patch("services.scheduler_service.scheduler_manager", fresh_manager):
        yield
        if fresh_manager.is_running:
            fresh_manager.stop(wait=False)


@pytest.mark.asyncio
async def test_get_scheduler_status(test_client: AsyncClient):
    """Test GET /api/v1/scheduler/status returns scheduler state."""
    response = await test_client.get("/api/v1/scheduler/status")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "data" in data
    assert "running" in data["data"]
    assert "paused" in data["data"]
    assert "job_count" in data["data"]


@pytest.mark.asyncio
async def test_start_scheduler(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/start starts the scheduler."""
    response = await test_client.post("/api/v1/scheduler/start")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["message"] == "Scheduler started with automation cycle"
    assert data["data"]["running"] is True

    # Clean up - stop the scheduler
    await test_client.post("/api/v1/scheduler/stop")


@pytest.mark.asyncio
async def test_stop_scheduler(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/stop stops the scheduler."""
    # First start the scheduler
    await test_client.post("/api/v1/scheduler/start")

    # Now stop it
    response = await test_client.post("/api/v1/scheduler/stop")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["message"] == "Scheduler stopped"
    assert data["data"]["running"] is False


@pytest.mark.asyncio
async def test_pause_scheduler(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/pause pauses the scheduler."""
    # First start the scheduler
    await test_client.post("/api/v1/scheduler/start")

    # Now pause it
    response = await test_client.post("/api/v1/scheduler/pause")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["message"] == "Scheduler paused"
    assert data["data"]["paused"] is True

    # Clean up
    await test_client.post("/api/v1/scheduler/stop")


@pytest.mark.asyncio
async def test_pause_scheduler_not_running(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/pause fails if not running."""
    # Make sure scheduler is stopped
    await test_client.post("/api/v1/scheduler/stop")

    response = await test_client.post("/api/v1/scheduler/pause")

    assert response.status_code == 400
    assert "not running" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_scheduler(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/resume resumes the scheduler."""
    # Start and pause the scheduler
    await test_client.post("/api/v1/scheduler/start")
    await test_client.post("/api/v1/scheduler/pause")

    # Now resume it
    response = await test_client.post("/api/v1/scheduler/resume")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["message"] == "Scheduler resumed"
    assert data["data"]["paused"] is False

    # Clean up
    await test_client.post("/api/v1/scheduler/stop")


@pytest.mark.asyncio
async def test_resume_scheduler_not_running(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/resume fails if not running."""
    # Make sure scheduler is stopped
    await test_client.post("/api/v1/scheduler/stop")

    response = await test_client.post("/api/v1/scheduler/resume")

    assert response.status_code == 400
    assert "not running" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_resume_scheduler_not_paused(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/resume fails if not paused."""
    # Start scheduler but don't pause
    await test_client.post("/api/v1/scheduler/start")

    response = await test_client.post("/api/v1/scheduler/resume")

    assert response.status_code == 400
    assert "not paused" in response.json()["detail"].lower()

    # Clean up
    await test_client.post("/api/v1/scheduler/stop")


@pytest.mark.asyncio
async def test_scan_requires_auth(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/scan returns skipped without auth."""
    # Without credentials, scan should return skipped status
    response = await test_client.post("/api/v1/scheduler/scan")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Without auth, should return skipped
    assert data["data"]["skipped"] is True
    assert data["data"]["reason"] == "not_authenticated"
    assert data["data"]["new"] == 0
    assert data["data"]["updated"] == 0


@pytest.mark.asyncio
async def test_quick_scan_requires_auth(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/scan/quick returns skipped without auth."""
    response = await test_client.post("/api/v1/scheduler/scan/quick")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Without auth, should return skipped
    assert data["data"]["skipped"] is True
    assert data["data"]["reason"] == "not_authenticated"


@pytest.mark.asyncio
async def test_process_requires_auth(test_client: AsyncClient):
    """Test POST /api/v1/scheduler/process returns skipped without auth."""
    response = await test_client.post("/api/v1/scheduler/process")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    # Without auth, should return skipped
    assert data["data"]["skipped"] is True


@pytest.mark.asyncio
async def test_scheduler_lifecycle(test_client: AsyncClient):
    """Test full scheduler lifecycle: start -> pause -> resume -> stop."""
    # Initial status - should be stopped
    response = await test_client.get("/api/v1/scheduler/status")
    assert response.json()["data"]["running"] is False

    # Start
    response = await test_client.post("/api/v1/scheduler/start")
    assert response.status_code == 200
    assert response.json()["data"]["running"] is True

    # Verify status
    response = await test_client.get("/api/v1/scheduler/status")
    assert response.json()["data"]["running"] is True
    assert response.json()["data"]["paused"] is False

    # Pause
    response = await test_client.post("/api/v1/scheduler/pause")
    assert response.status_code == 200
    assert response.json()["data"]["paused"] is True

    # Verify paused status
    response = await test_client.get("/api/v1/scheduler/status")
    assert response.json()["data"]["running"] is True
    assert response.json()["data"]["paused"] is True

    # Resume
    response = await test_client.post("/api/v1/scheduler/resume")
    assert response.status_code == 200
    assert response.json()["data"]["paused"] is False

    # Stop
    response = await test_client.post("/api/v1/scheduler/stop")
    assert response.status_code == 200
    assert response.json()["data"]["running"] is False

    # Final status
    response = await test_client.get("/api/v1/scheduler/status")
    assert response.json()["data"]["running"] is False


async def _seed_session_and_pending_giveaway(async_engine, end_time) -> None:
    """Store a PHPSESSID and one entered giveaway that ends at ``end_time``."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="PEND1", url="/giveaway/PEND1/", game_name="Pending", price=10,
                             end_time=end_time, is_entered=True))
        await session.commit()


@pytest.mark.asyncio
async def test_sync_wins_endpoint_answers_500_when_won_page_fails(
    test_client: AsyncClient, async_engine
) -> None:
    """POST /scheduler/sync-wins whose /giveaways/won answers 404 fails with
    500 naming the fetch error instead of answering 200 {new_wins: 0}; the
    PHPSESSID is not in the response."""
    await _seed_session_and_pending_giveaway(async_engine, utcnow() + timedelta(days=1))
    transport = RoutedTransport()
    transport.add("GET", "/", httpx.Response(200, text=(FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")))
    transport.add("GET", "/giveaways/won", httpx.Response(404, text="Not Found"))

    with (
        patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
        patch("workers.context.SteamClient", partial(SteamClient, transport=RoutedTransport())),
    ):
        response = await test_client.post("/api/v1/scheduler/sync-wins")

    assert response.status_code == 500, response.text
    assert "Failed to fetch won giveaways: 404" in response.text
    assert "test_session" not in response.text
    assert [r.url.path for r in transport.requests] == ["/", "/giveaways/won"]


@pytest.mark.asyncio
async def test_sync_wins_endpoint_reports_new_wins_on_success(
    test_client: AsyncClient, async_engine
) -> None:
    """POST /scheduler/sync-wins on a won page that loads answers 200 with the
    number of new wins, and the won giveaway is stored as won."""
    await _seed_session_and_pending_giveaway(async_engine, utcnow() - timedelta(days=1))
    won_page = (
        '<div class="table__row-outer-wrap"><div class="table__row-inner-wrap">'
        '<a class="table__column__heading" href="/giveaway/PEND1/pending">Pending</a>'
        '</div></div>'
    )
    transport = RoutedTransport()
    transport.add("GET", "/", httpx.Response(200, text=(FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")))
    transport.add("GET", "/giveaways/won", httpx.Response(200, text=won_page))

    with (
        patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=transport)),
        patch("workers.context.SteamClient", partial(SteamClient, transport=RoutedTransport())),
    ):
        response = await test_client.post("/api/v1/scheduler/sync-wins")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"new_wins": 1, "skipped": False}
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        won = await session.scalar(select(Giveaway).where(Giveaway.code == "PEND1"))
    assert won is not None and won.is_won is True


@pytest.mark.asyncio
@pytest.mark.usefixtures("non_utc_host")
async def test_status_endpoint_reports_win_check_next_run_in_utc_with_z(
    test_client: AsyncClient, async_engine
) -> None:
    """On a Europe/Paris host with a New York scheduler, GET /scheduler/status
    reports the win check at end time + 5 min in UTC with a Z suffix."""
    manager = SchedulerManager()
    manager.start()
    end_time = utcnow().replace(microsecond=0) + timedelta(days=1)
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        with (
            patch("api.routers.scheduler.scheduler_manager", manager),
            patch("services.scheduler_service.scheduler_manager", manager),
        ):
            async with session_maker() as session:
                await SchedulerService(session).update_win_check_for_new_entry(end_time)
            response = await test_client.get("/api/v1/scheduler/status")
    finally:
        manager.stop(wait=False)

    assert response.status_code == 200, response.text
    next_runs = {job["id"]: job["next_run"] for job in response.json()["data"]["jobs"]}
    assert next_runs[WIN_CHECK_JOB_ID] == (end_time + timedelta(minutes=5)).isoformat() + "Z"
