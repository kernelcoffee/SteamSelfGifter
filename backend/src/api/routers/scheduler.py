"""Scheduler API router for automation control.

This module provides REST API endpoints for scheduler management,
including start/stop, status, and manual trigger operations.
"""

from fastapi import APIRouter, HTTPException, status
from typing import Dict, Any

from api.schemas.common import create_success_response
from api.dependencies import SettingsServiceDep
from workers.scheduler import scheduler_manager
from workers.automation import automation_cycle, sync_wins_only
from workers.scanner import scan_giveaways, quick_scan
from workers.processor import process_giveaways, enter_single_giveaway
from workers.safety_checker import safety_check_cycle

router = APIRouter()


@router.get(
    "/status",
    response_model=Dict[str, Any],
    summary="Get scheduler status",
    description="Retrieve current scheduler status including running state and jobs.",
)
async def get_scheduler_status() -> Dict[str, Any]:
    """
    Get scheduler status.

    Returns:
        Success response with scheduler status

    Example response:
        {
            "success": true,
            "data": {
                "running": true,
                "paused": false,
                "job_count": 1,
                "jobs": [...]
            }
        }
    """
    status_data = scheduler_manager.get_status()
    return create_success_response(data=status_data)


@router.post(
    "/start",
    response_model=Dict[str, Any],
    summary="Start scheduler",
    description="Start the scheduler to begin automated operations.",
)
async def start_scheduler(settings_service: SettingsServiceDep) -> Dict[str, Any]:
    """
    Start the scheduler and schedule the automation cycle job.

    Returns:
        Success response with updated status
    """
    # Start the scheduler
    scheduler_manager.start()

    # Get settings to determine cycle interval
    settings = await settings_service.get_settings()
    cycle_interval_minutes = settings.scan_interval_minutes or 30

    # Remove any existing jobs (in case of restart)
    try:
        scheduler_manager.remove_job("automation_cycle")
    except Exception:
        pass

    # Legacy job cleanup
    try:
        scheduler_manager.remove_job("scan_giveaways")
    except Exception:
        pass

    try:
        scheduler_manager.remove_job("process_giveaways")
    except Exception:
        pass

    # Add the single automation cycle job
    scheduler_manager.add_interval_job(
        func=automation_cycle,
        job_id="automation_cycle",
        minutes=cycle_interval_minutes,
    )

    # Add safety check job if enabled (runs every 45 seconds)
    safety_check_enabled = False
    if settings.safety_check_enabled:
        try:
            scheduler_manager.remove_job("safety_check")
        except Exception:
            pass

        scheduler_manager.add_interval_job(
            func=safety_check_cycle,
            job_id="safety_check",
            seconds=45,
        )
        safety_check_enabled = True

    return create_success_response(
        data={
            "message": "Scheduler started with automation cycle",
            "running": scheduler_manager.is_running,
            "cycle_interval_minutes": cycle_interval_minutes,
            "safety_check_enabled": safety_check_enabled,
        }
    )


@router.post(
    "/stop",
    response_model=Dict[str, Any],
    summary="Stop scheduler",
    description="Stop the scheduler. Running jobs will complete.",
)
async def stop_scheduler() -> Dict[str, Any]:
    """
    Stop the scheduler.

    Returns:
        Success response with updated status
    """
    scheduler_manager.stop(wait=True)
    return create_success_response(
        data={
            "message": "Scheduler stopped",
            "running": scheduler_manager.is_running,
        }
    )


@router.post(
    "/pause",
    response_model=Dict[str, Any],
    summary="Pause scheduler",
    description="Pause scheduled jobs without stopping the scheduler.",
)
async def pause_scheduler() -> Dict[str, Any]:
    """
    Pause the scheduler.

    Returns:
        Success response with updated status
    """
    if not scheduler_manager.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduler is not running"
        )

    scheduler_manager.pause()
    return create_success_response(
        data={
            "message": "Scheduler paused",
            "paused": scheduler_manager.is_paused,
        }
    )


@router.post(
    "/resume",
    response_model=Dict[str, Any],
    summary="Resume scheduler",
    description="Resume paused scheduler jobs.",
)
async def resume_scheduler() -> Dict[str, Any]:
    """
    Resume the scheduler.

    Returns:
        Success response with updated status
    """
    if not scheduler_manager.is_running:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduler is not running"
        )

    if not scheduler_manager.is_paused:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Scheduler is not paused"
        )

    scheduler_manager.resume()
    return create_success_response(
        data={
            "message": "Scheduler resumed",
            "paused": scheduler_manager.is_paused,
        }
    )


# === Manual Trigger Endpoints ===


@router.post(
    "/run",
    response_model=Dict[str, Any],
    summary="Run automation cycle",
    description="Manually trigger a full automation cycle (scan + wishlist + wins + entries).",
)
async def trigger_automation_cycle() -> Dict[str, Any]:
    """
    Trigger a full automation cycle manually.

    Runs: scan giveaways → scan wishlist → sync wins → process entries

    Returns:
        Success response with cycle results
    """
    try:
        results = await automation_cycle()
        return create_success_response(data=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Automation cycle failed: {str(e)}"
        )


@router.post(
    "/scan",
    response_model=Dict[str, Any],
    summary="Trigger manual scan",
    description="Manually trigger a giveaway scan only.",
)
async def trigger_scan() -> Dict[str, Any]:
    """
    Trigger a manual giveaway scan.

    Returns:
        Success response with scan results
    """
    try:
        results = await scan_giveaways()
        return create_success_response(data=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Scan failed: {str(e)}"
        )


@router.post(
    "/scan/quick",
    response_model=Dict[str, Any],
    summary="Trigger quick scan",
    description="Manually trigger a quick scan (single page).",
)
async def trigger_quick_scan() -> Dict[str, Any]:
    """
    Trigger a quick scan (single page).

    Returns:
        Success response with scan results
    """
    try:
        results = await quick_scan()
        return create_success_response(data=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Quick scan failed: {str(e)}"
        )


@router.post(
    "/process",
    response_model=Dict[str, Any],
    summary="Trigger manual processing",
    description="Manually trigger giveaway processing to enter eligible giveaways.",
)
async def trigger_processing() -> Dict[str, Any]:
    """
    Trigger manual giveaway processing.

    Returns:
        Success response with processing results
    """
    try:
        results = await process_giveaways()
        return create_success_response(data=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}"
        )


@router.post(
    "/sync-wins",
    response_model=Dict[str, Any],
    summary="Sync wins",
    description="Manually sync wins from SteamGifts won page.",
)
async def trigger_sync_wins() -> Dict[str, Any]:
    """
    Trigger manual win sync.

    Returns:
        Success response with win sync results
    """
    try:
        results = await sync_wins_only()
        return create_success_response(data=results)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Win sync failed: {str(e)}"
        )


@router.post(
    "/enter/{giveaway_code}",
    response_model=Dict[str, Any],
    summary="Enter a giveaway",
    description="Manually enter a specific giveaway by code.",
)
async def enter_giveaway(giveaway_code: str) -> Dict[str, Any]:
    """
    Enter a specific giveaway.

    Args:
        giveaway_code: The giveaway code to enter

    Returns:
        Success response with entry result
    """
    result = await enter_single_giveaway(giveaway_code)

    if result["success"]:
        return create_success_response(data=result)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["error"]
        )
