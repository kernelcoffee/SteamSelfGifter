"""Integration tests for API endpoints against real SteamGifts.

Run with: pytest tests/integration/ --run-integration --phpsessid="YOUR_SESSION_ID"
"""

import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app
from db.session import AsyncSessionLocal, init_db


@pytest.fixture
async def setup_db():
    """Initialize database before tests."""
    await init_db()
    yield


@pytest.mark.integration
@pytest.mark.asyncio
class TestAPIEndpointsIntegration:
    """Integration tests for API endpoints with real SteamGifts."""

    async def test_settings_roundtrip(self, setup_db, phpsessid, user_agent):
        """Test saving and retrieving settings via API."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Save settings
            response = await client.put(
                "/api/v1/settings/",
                json={
                    "phpsessid": phpsessid,
                    "user_agent": user_agent,
                }
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert data["data"]["phpsessid"] == phpsessid

            # Retrieve settings
            response = await client.get("/api/v1/settings/")
            assert response.status_code == 200
            data = response.json()
            assert data["data"]["phpsessid"] == phpsessid

            print(f"\n  Settings saved and retrieved successfully")

    async def test_test_session_endpoint(self, setup_db, phpsessid, user_agent):
        """Test the test-session endpoint with real credentials."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # First save credentials
            await client.put(
                "/api/v1/settings/",
                json={
                    "phpsessid": phpsessid,
                    "user_agent": user_agent,
                }
            )

            # Test session
            response = await client.post("/api/v1/settings/test-session")
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert data["data"]["valid"] is True
            assert "username" in data["data"]
            assert "points" in data["data"]

            print(f"\n  Session test passed via API")
            print(f"  Username: {data['data']['username']}")
            print(f"  Points: {data['data']['points']}")

    async def test_giveaways_endpoint(self, setup_db, phpsessid, user_agent):
        """Test fetching giveaways via API."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Save credentials first
            await client.put(
                "/api/v1/settings/",
                json={
                    "phpsessid": phpsessid,
                    "user_agent": user_agent,
                }
            )

            # Get giveaways
            response = await client.get("/api/v1/giveaways/")
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True

            giveaways = data["data"].get("giveaways", [])
            count = data["data"].get("count", 0)

            print(f"\n  Fetched {len(giveaways)} giveaways from API")
            print(f"  Total count: {count}")

            if giveaways:
                ga = giveaways[0]
                print(f"  First: {ga.get('game_name', 'Unknown')} ({ga.get('points_cost', 0)}P)")

    async def test_system_health(self, setup_db):
        """Test system health endpoint."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/system/health")
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert data["data"]["status"] == "healthy"

            print(f"\n  System health: {data['data']['status']}")

    async def test_validate_configuration(self, setup_db, phpsessid, user_agent):
        """Test configuration validation endpoint."""
        transport = ASGITransport(app=app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Save valid credentials
            await client.put(
                "/api/v1/settings/",
                json={
                    "phpsessid": phpsessid,
                    "user_agent": user_agent,
                }
            )

            # Validate configuration
            response = await client.post("/api/v1/settings/validate")
            assert response.status_code == 200

            data = response.json()
            assert data["success"] is True
            assert "is_valid" in data["data"]

            print(f"\n  Configuration valid: {data['data']['is_valid']}")
            if data["data"].get("errors"):
                print(f"  Errors: {data['data']['errors']}")
            if data["data"].get("warnings"):
                print(f"  Warnings: {data['data']['warnings']}")
