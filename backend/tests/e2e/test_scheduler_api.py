"""End-to-end tests for scheduler API endpoints.

These drive the real FastAPI app + router + APScheduler against the in-memory
test database. Two pieces of wiring make that possible (see ``_wire_scheduler_e2e``):

- Worker jobs open their own DB session via ``workers.context.AsyncSessionLocal``
  (outside FastAPI's dependency injection), so it's patched onto the test engine.
- The router and service bind the module-level ``scheduler_manager`` at import,
  so each test gets a fresh, isolated ``SchedulerManager`` patched into both.
"""

import pytest
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from workers.scheduler import SchedulerManager


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
