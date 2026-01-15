"""
Unit tests for FastAPI main application.

Tests application initialization, middleware, exception handlers,
and basic endpoints.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from api.main import app
from core.exceptions import (
    ConfigurationError,
    InsufficientPointsError,
    RateLimitError,
    ResourceNotFoundError,
    SchedulerError,
    SteamAPIError,
    SteamGiftsError,
    ValidationError,
)


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_app_initialization():
    """Test that the FastAPI app is properly initialized."""
    assert app.title == "SteamSelfGifter"
    assert app.version == "2.0.0"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"


def test_root_endpoint(client):
    """Test root endpoint returns application info."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["app"] == "SteamSelfGifter"
    assert data["version"] == "2.0.0"
    assert data["status"] == "running"
    assert "environment" in data
    assert data["docs"] == "/docs"


def test_health_check_endpoint(client):
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


def test_openapi_schema_available(client):
    """Test that OpenAPI schema is available."""
    response = client.get("/openapi.json")
    assert response.status_code == status.HTTP_200_OK

    schema = response.json()
    assert schema["info"]["title"] == "SteamSelfGifter"
    assert schema["info"]["version"] == "2.0.0"


def test_docs_endpoint_available(client):
    """Test that Swagger docs are available."""
    response = client.get("/docs")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]


def test_redoc_endpoint_available(client):
    """Test that ReDoc is available."""
    response = client.get("/redoc")
    assert response.status_code == status.HTTP_200_OK
    assert "text/html" in response.headers["content-type"]


def test_cors_headers(client):
    """Test that CORS headers are set."""
    response = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access-control-allow-origin" in response.headers


@pytest.mark.skip(reason="Requires database setup - covered by e2e tests")
def test_settings_router_included(client):
    """Test that settings router is included."""
    # GET /api/v1/settings should exist (even if it returns error without DB)
    response = client.get("/api/v1/settings")
    # May return 500 if DB not set up, but route should exist
    assert response.status_code in [200, 500]


def test_system_router_included(client):
    """Test that system router is included."""
    response = client.get("/api/v1/system/health")
    assert response.status_code == status.HTTP_200_OK


def test_websocket_router_included():
    """Test that websocket router is included."""
    # WebSocket routes are registered
    routes = [route.path for route in app.routes]
    assert "/ws/events" in routes


def test_exception_handler_resource_not_found(client):
    """Test ResourceNotFoundError exception handler."""
    # Create a test endpoint that raises ResourceNotFoundError
    @app.get("/test/not-found")
    async def test_not_found():
        raise ResourceNotFoundError(
            message="Test resource not found", code="TEST_001"
        )

    response = client.get("/test/not-found")
    assert response.status_code == 404

    data = response.json()
    assert data["error"]["message"] == "Test resource not found"
    assert data["error"]["code"] == "TEST_001"


def test_exception_handler_validation_error(client):
    """Test ValidationError exception handler."""
    @app.get("/test/validation")
    async def test_validation():
        raise ValidationError(message="Invalid input", code="VAL_001")

    response = client.get("/test/validation")
    assert response.status_code == 422

    data = response.json()
    assert data["error"]["message"] == "Invalid input"
    assert data["error"]["code"] == "VAL_001"


def test_exception_handler_configuration_error(client):
    """Test ConfigurationError exception handler."""
    @app.get("/test/config")
    async def test_config():
        raise ConfigurationError(message="Config error", code="CONFIG_001")

    response = client.get("/test/config")
    assert response.status_code == 500

    data = response.json()
    assert data["error"]["message"] == "Config error"
    assert data["error"]["code"] == "CONFIG_001"


def test_exception_handler_steamgifts_error(client):
    """Test SteamGiftsError exception handler."""
    @app.get("/test/steamgifts")
    async def test_steamgifts():
        raise SteamGiftsError(message="SteamGifts error", code="SG_001")

    response = client.get("/test/steamgifts")
    assert response.status_code == 502

    data = response.json()
    assert data["error"]["message"] == "SteamGifts error"
    assert data["error"]["code"] == "SG_001"


def test_exception_handler_steam_api_error(client):
    """Test SteamAPIError exception handler."""
    @app.get("/test/steam")
    async def test_steam():
        raise SteamAPIError(message="Steam API error", code="STEAM_001")

    response = client.get("/test/steam")
    assert response.status_code == 502

    data = response.json()
    assert data["error"]["message"] == "Steam API error"
    assert data["error"]["code"] == "STEAM_001"


def test_exception_handler_insufficient_points(client):
    """Test InsufficientPointsError exception handler."""
    @app.get("/test/points")
    async def test_points():
        raise InsufficientPointsError(message="Not enough points", code="GIVE_004")

    response = client.get("/test/points")
    assert response.status_code == 402

    data = response.json()
    assert data["error"]["message"] == "Not enough points"
    assert data["error"]["code"] == "GIVE_004"


def test_exception_handler_rate_limit(client):
    """Test RateLimitError exception handler."""
    @app.get("/test/rate-limit")
    async def test_rate_limit():
        raise RateLimitError(message="Rate limit exceeded", code="SG_001")

    response = client.get("/test/rate-limit")
    assert response.status_code == 429

    data = response.json()
    assert data["error"]["message"] == "Rate limit exceeded"
    assert data["error"]["code"] == "SG_001"


def test_exception_handler_scheduler_error(client):
    """Test SchedulerError exception handler."""
    @app.get("/test/scheduler")
    async def test_scheduler():
        raise SchedulerError(message="Scheduler error", code="SCHED_001")

    response = client.get("/test/scheduler")
    assert response.status_code == 409

    data = response.json()
    assert data["error"]["message"] == "Scheduler error"
    assert data["error"]["code"] == "SCHED_001"


def test_exception_handler_unhandled():
    """Test unhandled exception handler is registered."""
    # Verify that the generic Exception handler is registered
    exception_handlers = app.exception_handlers
    assert Exception in exception_handlers

    # The handler should be the unhandled_exception_handler
    from api.middleware import unhandled_exception_handler
    assert exception_handlers[Exception] == unhandled_exception_handler


def test_404_not_found(client):
    """Test that unknown routes return 404."""
    response = client.get("/this/route/does/not/exist")
    assert response.status_code == 404


@pytest.mark.skip(reason="Requires database setup - covered by e2e tests")
def test_api_prefix(client):
    """Test that API endpoints use correct prefix."""
    # Settings endpoint
    response = client.get("/api/v1/settings")
    assert response.status_code in [200, 500]  # Route exists

    # System health endpoint
    response = client.get("/api/v1/system/health")
    assert response.status_code == 200


def test_root_endpoint_fields(client):
    """Test that root endpoint includes all expected fields."""
    response = client.get("/")
    data = response.json()

    expected_fields = ["app", "version", "status", "environment", "docs"]
    for field in expected_fields:
        assert field in data


def test_multiple_requests(client):
    """Test that app handles multiple requests correctly."""
    for _ in range(5):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
