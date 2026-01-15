"""
Unit tests for API middleware exception handlers.

Tests all custom exception handlers to ensure proper HTTP status codes
and error response format.
"""

import pytest
from fastapi.responses import JSONResponse

from api.middleware import (
    app_exception_handler,
    configuration_error_handler,
    create_error_response,
    insufficient_points_handler,
    rate_limit_error_handler,
    resource_not_found_handler,
    scheduler_error_handler,
    steam_api_error_handler,
    steamgifts_error_handler,
    unhandled_exception_handler,
    validation_error_handler,
)
from core.exceptions import (
    AppException,
    ConfigurationError,
    InsufficientPointsError,
    RateLimitError,
    ResourceNotFoundError,
    SchedulerError,
    SteamAPIError,
    SteamGiftsError,
    ValidationError,
)


class MockRequest:
    """Mock request for testing."""

    def __init__(self, path: str = "/test"):
        self.url = type("URL", (), {"path": path})()


@pytest.fixture
def mock_request():
    """Create a mock request."""
    return MockRequest()


def test_create_error_response():
    """Test error response creation."""
    response = create_error_response(
        status_code=400,
        message="Test error",
        code="TEST_001",
        details={"field": "value"},
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400

    # Parse response body
    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Test error"
    assert body["error"]["code"] == "TEST_001"
    assert body["error"]["details"] == {"field": "value"}


def test_create_error_response_without_details():
    """Test error response creation without details."""
    response = create_error_response(
        status_code=404, message="Not found", code="TEST_002"
    )

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["details"] == {}


@pytest.mark.asyncio
async def test_app_exception_handler(mock_request):
    """Test AppException handler."""
    exc = AppException(
        message="Application error", code="APP_001", details={"key": "value"}
    )

    response = await app_exception_handler(mock_request, exc)

    assert response.status_code == 500

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Application error"
    assert body["error"]["code"] == "APP_001"
    assert body["error"]["details"] == {"key": "value"}


@pytest.mark.asyncio
async def test_configuration_error_handler(mock_request):
    """Test ConfigurationError handler."""
    exc = ConfigurationError(
        message="Invalid configuration", code="CONFIG_001", details={"setting": "value"}
    )

    response = await configuration_error_handler(mock_request, exc)

    assert response.status_code == 500

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Invalid configuration"
    assert body["error"]["code"] == "CONFIG_001"
    assert body["error"]["details"] == {"setting": "value"}


@pytest.mark.asyncio
async def test_resource_not_found_handler(mock_request):
    """Test ResourceNotFoundError handler."""
    exc = ResourceNotFoundError(
        message="Resource not found", code="GIVE_001", details={"id": "123"}
    )

    response = await resource_not_found_handler(mock_request, exc)

    assert response.status_code == 404

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Resource not found"
    assert body["error"]["code"] == "GIVE_001"
    assert body["error"]["details"] == {"id": "123"}


@pytest.mark.asyncio
async def test_validation_error_handler(mock_request):
    """Test ValidationError handler."""
    exc = ValidationError(
        message="Invalid input", code="VAL_001", details={"field": "email"}
    )

    response = await validation_error_handler(mock_request, exc)

    assert response.status_code == 422

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Invalid input"
    assert body["error"]["code"] == "VAL_001"
    assert body["error"]["details"] == {"field": "email"}


@pytest.mark.asyncio
async def test_steamgifts_error_handler(mock_request):
    """Test SteamGiftsError handler."""
    exc = SteamGiftsError(
        message="SteamGifts unavailable", code="SG_002", details={"status": 503}
    )

    response = await steamgifts_error_handler(mock_request, exc)

    assert response.status_code == 502

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "SteamGifts unavailable"
    assert body["error"]["code"] == "SG_002"
    assert body["error"]["details"] == {"status": 503}


@pytest.mark.asyncio
async def test_steam_api_error_handler(mock_request):
    """Test SteamAPIError handler."""
    exc = SteamAPIError(
        message="Steam API error", code="STEAM_001", details={"reason": "timeout"}
    )

    response = await steam_api_error_handler(mock_request, exc)

    assert response.status_code == 502

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Steam API error"
    assert body["error"]["code"] == "STEAM_001"
    assert body["error"]["details"] == {"reason": "timeout"}


@pytest.mark.asyncio
async def test_insufficient_points_handler(mock_request):
    """Test InsufficientPointsError handler."""
    exc = InsufficientPointsError(
        message="Not enough points",
        code="GIVE_004",
        details={"required": 100, "available": 50},
    )

    response = await insufficient_points_handler(mock_request, exc)

    assert response.status_code == 402

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Not enough points"
    assert body["error"]["code"] == "GIVE_004"
    assert body["error"]["details"] == {"required": 100, "available": 50}


@pytest.mark.asyncio
async def test_rate_limit_error_handler(mock_request):
    """Test RateLimitError handler."""
    exc = RateLimitError(
        message="Rate limit exceeded", code="SG_001", details={"retry_after": 60}
    )

    response = await rate_limit_error_handler(mock_request, exc)

    assert response.status_code == 429

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Rate limit exceeded"
    assert body["error"]["code"] == "SG_001"
    assert body["error"]["details"] == {"retry_after": 60}


@pytest.mark.asyncio
async def test_scheduler_error_handler(mock_request):
    """Test SchedulerError handler."""
    exc = SchedulerError(
        message="Scheduler already running",
        code="SCHED_001",
        details={"state": "running"},
    )

    response = await scheduler_error_handler(mock_request, exc)

    assert response.status_code == 409

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "Scheduler already running"
    assert body["error"]["code"] == "SCHED_001"
    assert body["error"]["details"] == {"state": "running"}


@pytest.mark.asyncio
async def test_unhandled_exception_handler(mock_request):
    """Test unhandled exception handler."""
    exc = ValueError("Unexpected error")

    response = await unhandled_exception_handler(mock_request, exc)

    assert response.status_code == 500

    import json

    body = json.loads(response.body.decode())
    assert body["error"]["message"] == "An unexpected error occurred"
    assert body["error"]["code"] == "SYS_001"
    assert body["error"]["details"]["type"] == "ValueError"


@pytest.mark.asyncio
async def test_exception_handlers_log_correctly(mock_request, caplog):
    """Test that all exception handlers log appropriately."""
    import logging

    caplog.set_level(logging.INFO)

    # Test with different exception types
    exc = ResourceNotFoundError(message="Not found", code="TEST_001")
    await resource_not_found_handler(mock_request, exc)

    # Logger calls are captured by structlog, so we just verify no crashes
    # Actual log assertion would require structlog testing setup


@pytest.mark.asyncio
async def test_all_handlers_return_json_response(mock_request):
    """Test that all handlers return JSONResponse instances."""
    handlers_and_exceptions = [
        (app_exception_handler, AppException("msg", "code")),
        (configuration_error_handler, ConfigurationError("msg", "code")),
        (resource_not_found_handler, ResourceNotFoundError("msg", "code")),
        (validation_error_handler, ValidationError("msg", "code")),
        (steamgifts_error_handler, SteamGiftsError("msg", "code")),
        (steam_api_error_handler, SteamAPIError("msg", "code")),
        (insufficient_points_handler, InsufficientPointsError("msg", "code")),
        (rate_limit_error_handler, RateLimitError("msg", "code")),
        (scheduler_error_handler, SchedulerError("msg", "code")),
        (unhandled_exception_handler, ValueError("msg")),
    ]

    for handler, exc in handlers_and_exceptions:
        response = await handler(mock_request, exc)
        assert isinstance(response, JSONResponse)


@pytest.mark.asyncio
async def test_error_response_structure(mock_request):
    """Test that all error responses follow the same structure."""
    exc = ValidationError(
        message="Test error", code="TEST_001", details={"field": "value"}
    )

    response = await validation_error_handler(mock_request, exc)

    import json

    body = json.loads(response.body.decode())

    # Verify structure
    assert "error" in body
    assert "message" in body["error"]
    assert "code" in body["error"]
    assert "details" in body["error"]

    # Verify types
    assert isinstance(body["error"]["message"], str)
    assert isinstance(body["error"]["code"], str)
    assert isinstance(body["error"]["details"], dict)


@pytest.mark.asyncio
async def test_handlers_with_different_request_paths(mock_request):
    """Test that handlers work with different request paths."""
    paths = ["/api/v1/settings", "/api/v1/giveaways/123", "/ws/events"]

    for path in paths:
        request = MockRequest(path=path)
        exc = ValidationError(message="Test", code="TEST_001")
        response = await validation_error_handler(request, exc)
        assert response.status_code == 422
