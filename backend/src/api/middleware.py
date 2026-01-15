"""
Global exception handlers for the API.

Maps custom exceptions to appropriate HTTP responses with structured error format.
"""

from typing import Any

import structlog
from fastapi import Request, status
from fastapi.responses import JSONResponse

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
from core.events import event_manager

logger = structlog.get_logger()


def create_error_response(
    status_code: int,
    message: str,
    code: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        status_code: HTTP status code
        message: Human-readable error message
        code: Application error code
        details: Additional error details

    Returns:
        JSONResponse with error information
    """
    content = {
        "error": {
            "message": message,
            "code": code,
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=content)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Handler for base AppException.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 500 status code
    """
    logger.error(
        "app_exception",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def configuration_error_handler(
    request: Request, exc: ConfigurationError
) -> JSONResponse:
    """
    Handler for ConfigurationError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 500 status code
    """
    logger.error(
        "configuration_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def resource_not_found_handler(
    request: Request, exc: ResourceNotFoundError
) -> JSONResponse:
    """
    Handler for ResourceNotFoundError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 404 status code
    """
    logger.warning(
        "resource_not_found",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_404_NOT_FOUND,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def validation_error_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    """
    Handler for ValidationError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 422 status code
    """
    logger.warning(
        "validation_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=422,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def steamgifts_session_expired_handler(
    request: Request, exc: SteamGiftsSessionExpiredError
) -> JSONResponse:
    """
    Handler for SteamGiftsSessionExpiredError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 401 status code (Unauthorized)
    """
    logger.warning(
        "steamgifts_session_expired",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )

    # Broadcast session invalid event via WebSocket
    await event_manager.broadcast_session_invalid(
        reason=exc.message,
        error_code=exc.code,
    )

    return create_error_response(
        status_code=status.HTTP_401_UNAUTHORIZED,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def steamgifts_not_configured_handler(
    request: Request, exc: SteamGiftsNotConfiguredError
) -> JSONResponse:
    """
    Handler for SteamGiftsNotConfiguredError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 503 status code (Service Unavailable - needs configuration)
    """
    logger.warning(
        "steamgifts_not_configured",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def steamgifts_error_handler(
    request: Request, exc: SteamGiftsError
) -> JSONResponse:
    """
    Handler for SteamGiftsError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 502 status code
    """
    logger.error(
        "steamgifts_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def steam_api_error_handler(
    request: Request, exc: SteamAPIError
) -> JSONResponse:
    """
    Handler for SteamAPIError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 502 status code
    """
    logger.error(
        "steam_api_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_502_BAD_GATEWAY,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def insufficient_points_handler(
    request: Request, exc: InsufficientPointsError
) -> JSONResponse:
    """
    Handler for InsufficientPointsError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 402 status code
    """
    logger.warning(
        "insufficient_points",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def rate_limit_error_handler(
    request: Request, exc: RateLimitError
) -> JSONResponse:
    """
    Handler for RateLimitError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 429 status code
    """
    logger.warning(
        "rate_limit_exceeded",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def scheduler_error_handler(
    request: Request, exc: SchedulerError
) -> JSONResponse:
    """
    Handler for SchedulerError.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 409 status code
    """
    logger.error(
        "scheduler_error",
        code=exc.code,
        message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_409_CONFLICT,
        message=exc.message,
        code=exc.code,
        details=exc.details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Handler for unhandled exceptions.

    Args:
        request: The request that caused the exception
        exc: The exception instance

    Returns:
        JSONResponse with 500 status code
    """
    logger.exception(
        "unhandled_exception",
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        path=request.url.path,
    )
    return create_error_response(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        message="An unexpected error occurred",
        code="SYS_001",
        details={"type": type(exc).__name__},
    )
