"""Unit tests for scheduler API router."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from api.routers.scheduler import (
    get_scheduler_status,
    start_scheduler,
    stop_scheduler,
    pause_scheduler,
    resume_scheduler,
    trigger_scan,
    trigger_quick_scan,
    trigger_processing,
    enter_giveaway,
)


@pytest.mark.asyncio
async def test_get_scheduler_status():
    """Test GET /scheduler/status endpoint."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.get_status.return_value = {
            "running": True,
            "paused": False,
            "job_count": 2,
            "jobs": [],
        }

        result = await get_scheduler_status()

        assert result["success"] is True
        assert result["data"]["running"] is True
        assert result["data"]["paused"] is False


@pytest.mark.asyncio
async def test_start_scheduler():
    """Test POST /scheduler/start endpoint."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = True

        # Create mock settings service
        mock_settings_service = AsyncMock()
        mock_settings = MagicMock()
        mock_settings.scan_interval_minutes = 30
        mock_settings_service.get_settings = AsyncMock(return_value=mock_settings)

        result = await start_scheduler(mock_settings_service)

        assert result["success"] is True
        assert result["data"]["message"] == "Scheduler started with automation cycle"
        assert result["data"]["running"] is True
        mock_manager.start.assert_called_once()


@pytest.mark.asyncio
async def test_stop_scheduler():
    """Test POST /scheduler/stop endpoint."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = False

        result = await stop_scheduler()

        assert result["success"] is True
        assert result["data"]["message"] == "Scheduler stopped"
        assert result["data"]["running"] is False
        mock_manager.stop.assert_called_once_with(wait=True)


@pytest.mark.asyncio
async def test_pause_scheduler():
    """Test POST /scheduler/pause endpoint."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = True
        mock_manager.is_paused = True

        result = await pause_scheduler()

        assert result["success"] is True
        assert result["data"]["message"] == "Scheduler paused"
        mock_manager.pause.assert_called_once()


@pytest.mark.asyncio
async def test_pause_scheduler_not_running():
    """Test pause when scheduler not running."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = False

        with pytest.raises(HTTPException) as exc_info:
            await pause_scheduler()

        assert exc_info.value.status_code == 400
        assert "not running" in exc_info.value.detail


@pytest.mark.asyncio
async def test_resume_scheduler():
    """Test POST /scheduler/resume endpoint."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = True
        # is_paused is True initially (paused), then becomes False after resume
        type(mock_manager).is_paused = property(
            lambda self: mock_manager._paused_state
        )
        mock_manager._paused_state = True  # Initial state: paused

        def resume_effect():
            mock_manager._paused_state = False

        mock_manager.resume.side_effect = resume_effect

        result = await resume_scheduler()

        assert result["success"] is True
        assert result["data"]["message"] == "Scheduler resumed"
        mock_manager.resume.assert_called_once()


@pytest.mark.asyncio
async def test_resume_scheduler_not_running():
    """Test resume when scheduler not running."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = False

        with pytest.raises(HTTPException) as exc_info:
            await resume_scheduler()

        assert exc_info.value.status_code == 400
        assert "not running" in exc_info.value.detail


@pytest.mark.asyncio
async def test_resume_scheduler_not_paused():
    """Test resume when scheduler not paused."""
    with patch("api.routers.scheduler.scheduler_manager") as mock_manager:
        mock_manager.is_running = True
        mock_manager.is_paused = False

        with pytest.raises(HTTPException) as exc_info:
            await resume_scheduler()

        assert exc_info.value.status_code == 400
        assert "not paused" in exc_info.value.detail


@pytest.mark.asyncio
async def test_trigger_scan():
    """Test POST /scheduler/scan endpoint."""
    with patch("api.routers.scheduler.scan_giveaways") as mock_scan:
        mock_scan.return_value = {
            "new": 5,
            "updated": 2,
            "pages_scanned": 3,
            "scan_time": 1.5,
            "skipped": False,
        }

        result = await trigger_scan()

        assert result["success"] is True
        assert result["data"]["new"] == 5
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_scan_error():
    """Test scan endpoint with error."""
    with patch("api.routers.scheduler.scan_giveaways") as mock_scan:
        mock_scan.side_effect = Exception("Scan error")

        with pytest.raises(HTTPException) as exc_info:
            await trigger_scan()

        assert exc_info.value.status_code == 500
        assert "Scan failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_trigger_quick_scan():
    """Test POST /scheduler/scan/quick endpoint."""
    with patch("api.routers.scheduler.quick_scan") as mock_scan:
        mock_scan.return_value = {
            "new": 2,
            "updated": 1,
            "pages_scanned": 1,
            "scan_time": 0.5,
            "skipped": False,
        }

        result = await trigger_quick_scan()

        assert result["success"] is True
        assert result["data"]["pages_scanned"] == 1
        mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_processing():
    """Test POST /scheduler/process endpoint."""
    with patch("api.routers.scheduler.process_giveaways") as mock_process:
        mock_process.return_value = {
            "eligible": 5,
            "entered": 3,
            "failed": 0,
            "points_spent": 150,
            "skipped": False,
        }

        result = await trigger_processing()

        assert result["success"] is True
        assert result["data"]["entered"] == 3
        mock_process.assert_called_once()


@pytest.mark.asyncio
async def test_trigger_processing_error():
    """Test process endpoint with error."""
    with patch("api.routers.scheduler.process_giveaways") as mock_process:
        mock_process.side_effect = Exception("Processing error")

        with pytest.raises(HTTPException) as exc_info:
            await trigger_processing()

        assert exc_info.value.status_code == 500
        assert "Processing failed" in exc_info.value.detail


@pytest.mark.asyncio
async def test_enter_giveaway_success():
    """Test POST /scheduler/enter/{code} endpoint."""
    with patch("api.routers.scheduler.enter_single_giveaway") as mock_enter:
        mock_enter.return_value = {
            "success": True,
            "points_spent": 50,
            "error": None,
        }

        result = await enter_giveaway("TEST123")

        assert result["success"] is True
        assert result["data"]["points_spent"] == 50
        mock_enter.assert_called_once_with("TEST123")


@pytest.mark.asyncio
async def test_enter_giveaway_failure():
    """Test enter endpoint with failure."""
    with patch("api.routers.scheduler.enter_single_giveaway") as mock_enter:
        mock_enter.return_value = {
            "success": False,
            "points_spent": 0,
            "error": "Not enough points",
        }

        with pytest.raises(HTTPException) as exc_info:
            await enter_giveaway("TEST123")

        assert exc_info.value.status_code == 400
        assert "Not enough points" in exc_info.value.detail
