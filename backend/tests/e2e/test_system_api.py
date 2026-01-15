"""End-to-end tests for system API endpoints."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root_endpoint(test_client: AsyncClient):
    """Test GET / returns app info."""
    response = await test_client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["app"] == "SteamSelfGifter"
    assert "version" in data
    assert data["status"] == "running"


@pytest.mark.asyncio
async def test_health_check(test_client: AsyncClient):
    """Test GET /health returns ok status."""
    response = await test_client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_system_health(test_client: AsyncClient):
    """Test GET /api/v1/system/health returns detailed health info."""
    response = await test_client.get("/api/v1/system/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "status" in data["data"]
    assert data["data"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_system_info(test_client: AsyncClient):
    """Test GET /api/v1/system/info returns system information."""
    response = await test_client.get("/api/v1/system/info")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "app_name" in data["data"]
    assert "version" in data["data"]
    assert data["data"]["app_name"] == "SteamSelfGifter"


@pytest.mark.asyncio
async def test_system_logs_empty(test_client: AsyncClient):
    """Test GET /api/v1/system/logs returns empty list when no logs."""
    response = await test_client.get("/api/v1/system/logs")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "logs" in data["data"]
    assert isinstance(data["data"]["logs"], list)


@pytest.mark.asyncio
async def test_system_logs_with_level_filter(test_client: AsyncClient):
    """Test GET /api/v1/system/logs with level filter."""
    response = await test_client.get("/api/v1/system/logs?level=error")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_system_logs_with_limit(test_client: AsyncClient):
    """Test GET /api/v1/system/logs with custom limit."""
    response = await test_client.get("/api/v1/system/logs?limit=10")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True


@pytest.mark.asyncio
async def test_openapi_schema(test_client: AsyncClient):
    """Test GET /openapi.json returns OpenAPI schema."""
    response = await test_client.get("/openapi.json")

    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "paths" in data
    assert "info" in data
    assert data["info"]["title"] == "SteamSelfGifter"


@pytest.mark.asyncio
async def test_404_not_found(test_client: AsyncClient):
    """Test non-existent endpoint returns 404."""
    response = await test_client.get("/api/v1/nonexistent")

    assert response.status_code == 404
