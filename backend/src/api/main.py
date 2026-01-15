"""
FastAPI main application.

Creates and configures the FastAPI application with:
- CORS middleware
- Exception handlers
- API routers
- Lifespan events for startup/shutdown
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import (
    app_exception_handler,
    configuration_error_handler,
    insufficient_points_handler,
    rate_limit_error_handler,
    resource_not_found_handler,
    scheduler_error_handler,
    steam_api_error_handler,
    steamgifts_error_handler,
    steamgifts_session_expired_handler,
    steamgifts_not_configured_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from api.routers import settings as settings_router
from api.routers import system, websocket, scheduler, giveaways, games, entries, analytics
from core.config import settings
from core.exceptions import (
    AppException,
    ConfigurationError,
    InsufficientPointsError,
    RateLimitError,
    ResourceNotFoundError,
    SchedulerError,
    SteamAPIError,
    SteamGiftsError,
    SteamGiftsSessionExpiredError,
    SteamGiftsNotConfiguredError,
    ValidationError,
)
from core.logging import setup_logging

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.

    Handles startup and shutdown events:
    - Startup: Initialize logging, auto-start scheduler if enabled
    - Shutdown: Stop scheduler, cleanup resources
    """
    from db.session import AsyncSessionLocal, init_db
    from services.settings_service import SettingsService
    from workers.scheduler import scheduler_manager
    from workers.automation import automation_cycle
    from workers.safety_checker import safety_check_cycle

    # Startup
    setup_logging()

    # Initialize database (create tables if they don't exist)
    await init_db()
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        version=settings.version,
        environment=settings.environment,
    )

    # Check if automation should auto-start
    try:
        async with AsyncSessionLocal() as session:
            settings_service = SettingsService(session)
            app_settings = await settings_service.get_settings()

            if app_settings.automation_enabled:
                logger.info("auto_starting_scheduler")

                # Start the scheduler
                scheduler_manager.start()

                # Get scan interval
                scan_interval = app_settings.scan_interval_minutes or 30

                # Add the single automation cycle job
                scheduler_manager.add_interval_job(
                    func=automation_cycle,
                    job_id="automation_cycle",
                    minutes=scan_interval,
                )

                # Add safety check job (runs every 45 seconds, slow rate to avoid rate limits)
                if app_settings.safety_check_enabled:
                    scheduler_manager.add_interval_job(
                        func=safety_check_cycle,
                        job_id="safety_check",
                        seconds=45,
                    )
                    logger.info("safety_check_job_started", interval_seconds=45)

                logger.info(
                    "scheduler_auto_started",
                    cycle_interval_minutes=scan_interval,
                )
    except Exception as e:
        logger.error("scheduler_auto_start_failed", error=str(e))

    yield

    # Shutdown
    if scheduler_manager.is_running:
        logger.info("stopping_scheduler")
        scheduler_manager.stop(wait=True)

    logger.info("application_shutdown")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Automated SteamGifts bot backend with REST API",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    redirect_slashes=False,  # Prevent 307 redirects that break nginx proxy
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(ConfigurationError, configuration_error_handler)
app.add_exception_handler(ResourceNotFoundError, resource_not_found_handler)
app.add_exception_handler(ValidationError, validation_error_handler)
app.add_exception_handler(SteamGiftsSessionExpiredError, steamgifts_session_expired_handler)
app.add_exception_handler(SteamGiftsNotConfiguredError, steamgifts_not_configured_handler)
app.add_exception_handler(SteamGiftsError, steamgifts_error_handler)
app.add_exception_handler(SteamAPIError, steam_api_error_handler)
app.add_exception_handler(InsufficientPointsError, insufficient_points_handler)
app.add_exception_handler(RateLimitError, rate_limit_error_handler)
app.add_exception_handler(SchedulerError, scheduler_error_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

# Include API routers
app.include_router(
    settings_router.router,
    prefix=f"{settings.api_v1_prefix}/settings",
    tags=["settings"],
)
app.include_router(
    system.router,
    prefix=f"{settings.api_v1_prefix}/system",
    tags=["system"],
)
app.include_router(
    websocket.router,
    prefix="/ws",
    tags=["websocket"],
)
app.include_router(
    scheduler.router,
    prefix=f"{settings.api_v1_prefix}/scheduler",
    tags=["scheduler"],
)

app.include_router(
    giveaways.router,
    prefix=f"{settings.api_v1_prefix}/giveaways",
    tags=["giveaways"],
)
app.include_router(
    games.router,
    prefix=f"{settings.api_v1_prefix}/games",
    tags=["games"],
)
app.include_router(
    entries.router,
    prefix=f"{settings.api_v1_prefix}/entries",
    tags=["entries"],
)
app.include_router(
    analytics.router,
    prefix=f"{settings.api_v1_prefix}/analytics",
    tags=["analytics"],
)


@app.get("/", tags=["root"])
async def root():
    """
    Root endpoint.

    Returns basic application information.
    """
    return {
        "app": settings.app_name,
        "version": settings.version,
        "status": "running",
        "environment": settings.environment,
        "docs": "/docs",
    }


@app.get("/health", tags=["root"])
async def health_check():
    """
    Simple health check endpoint.

    Returns OK status for basic health monitoring.
    """
    return {"status": "ok"}
