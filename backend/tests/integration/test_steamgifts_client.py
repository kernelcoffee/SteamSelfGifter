"""Integration tests for SteamGifts client against real website.

Run with: pytest tests/integration/ --run-integration --phpsessid="YOUR_SESSION_ID"
Or set STEAMGIFTS_PHPSESSID environment variable.
"""

import pytest
from utils.steamgifts_client import SteamGiftsClient
from core.exceptions import SteamGiftsAuthError


@pytest.mark.integration
@pytest.mark.asyncio
class TestSteamGiftsClientIntegration:
    """Integration tests for SteamGiftsClient with real SteamGifts."""

    async def test_get_user_info_valid_session(self, phpsessid, user_agent):
        """Test fetching user info with valid session."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            user_info = await client.get_user_info()

            assert "username" in user_info
            assert "points" in user_info
            assert isinstance(user_info["username"], str)
            assert len(user_info["username"]) > 0
            assert isinstance(user_info["points"], int)
            assert user_info["points"] >= 0

            print(f"\n  Username: {user_info['username']}")
            print(f"  Points: {user_info['points']}")

    async def test_get_user_points_valid_session(self, phpsessid, user_agent):
        """Test fetching points with valid session."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            points = await client.get_user_points()

            assert isinstance(points, int)
            assert points >= 0
            print(f"\n  Current points: {points}")

    async def test_get_giveaways(self, phpsessid, user_agent):
        """Test fetching giveaways list."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            giveaways = await client.get_giveaways(page=1)

            assert isinstance(giveaways, list)
            # There should always be some active giveaways
            assert len(giveaways) > 0

            print(f"\n  Found {len(giveaways)} giveaways on page 1")

            # Check first giveaway structure
            ga = giveaways[0]
            assert "code" in ga
            assert "game_name" in ga
            assert "price" in ga

            print(f"  First giveaway: {ga['game_name']} ({ga['price']}P)")

    async def test_get_multiple_pages(self, phpsessid, user_agent):
        """Test fetching multiple pages of giveaways."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            page1 = await client.get_giveaways(page=1)
            page2 = await client.get_giveaways(page=2)

            assert len(page1) > 0
            assert len(page2) > 0

            # Pages should have different giveaways (by code)
            codes1 = {ga["code"] for ga in page1}
            codes2 = {ga["code"] for ga in page2}

            # There might be some overlap due to timing, but not complete
            assert codes1 != codes2

            print(f"\n  Page 1: {len(page1)} giveaways")
            print(f"  Page 2: {len(page2)} giveaways")
            print(f"  Unique codes: {len(codes1 | codes2)}")

    async def test_xsrf_token_extraction(self, phpsessid, user_agent):
        """Test that XSRF token is extracted on start."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        assert client.xsrf_token is None

        async with client:
            # After start, XSRF token should be populated
            assert client.xsrf_token is not None
            assert len(client.xsrf_token) > 0

            print(f"\n  XSRF token extracted: {client.xsrf_token[:20]}...")

    async def test_invalid_session(self, user_agent):
        """Test that invalid session raises appropriate error."""
        client = SteamGiftsClient(
            phpsessid="invalid_session_id_12345",
            user_agent=user_agent,
        )

        with pytest.raises(SteamGiftsAuthError):
            async with client:
                await client.get_user_info()


@pytest.mark.integration
@pytest.mark.asyncio
class TestGiveawayParsing:
    """Test giveaway data parsing from real pages."""

    async def test_giveaway_fields(self, phpsessid, user_agent):
        """Test that giveaway objects have expected fields."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            giveaways = await client.get_giveaways(page=1)

            for ga in giveaways[:5]:  # Check first 5
                # Required fields
                assert "code" in ga, "Missing 'code' field"
                assert "game_name" in ga, "Missing 'game_name' field"
                assert "price" in ga, "Missing 'price' field"

                # Type checks
                assert isinstance(ga["code"], str)
                assert len(ga["code"]) > 0
                assert isinstance(ga["game_name"], str)
                assert isinstance(ga["price"], int)
                assert ga["price"] >= 0

                # Optional fields
                if ga.get("entries") is not None:
                    assert isinstance(ga["entries"], int)
                if ga.get("copies") is not None:
                    assert isinstance(ga["copies"], int)
                if ga.get("end_time") is not None:
                    from datetime import datetime
                    assert isinstance(ga["end_time"], datetime)

                print(f"\n  {ga['game_name']}: {ga['price']}P, code={ga['code']}")

    async def test_search_giveaways(self, phpsessid, user_agent):
        """Test searching for specific giveaways."""
        client = SteamGiftsClient(
            phpsessid=phpsessid,
            user_agent=user_agent,
        )

        async with client:
            # Search for a common game type
            giveaways = await client.get_giveaways(page=1, search_query="indie")

            print(f"\n  Found {len(giveaways)} giveaways matching 'indie'")

            # Results may vary, but the request should succeed
            assert isinstance(giveaways, list)
