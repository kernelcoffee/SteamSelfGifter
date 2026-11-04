"""Steam API client with async support and rate limiting.

This module provides an async HTTP client for Steam API operations with
automatic rate limiting, retry logic, and error handling.
"""

import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

import httpx
import structlog

from core.time import utcnow

logger = structlog.get_logger()

# Upper bound on a review count read from Steam: far above any real app (the
# most reviewed ones have a few million), and small enough that the service's
# total_positive + total_negative still fits SQLite's 64-bit INTEGER.
MAX_REVIEW_COUNT = 2**31 - 1

# The query_summary fields get_app_reviews returns, each with the largest
# value accepted (review_score is Steam's 0-9 summary bucket). Steam's other
# fields (review_score_desc, num_reviews) are not stored.
REVIEW_SUMMARY_LIMITS = {
    "review_score": 9,
    "total_positive": MAX_REVIEW_COUNT,
    "total_negative": MAX_REVIEW_COUNT,
    "total_reviews": MAX_REVIEW_COUNT,
}


class RateLimiter:
    """
    Simple rate limiter for API calls.

    Ensures we don't exceed Steam API rate limits by tracking
    call timestamps and enforcing delays when necessary.

    Design Notes:
        - Uses sliding window approach
        - Thread-safe with asyncio.Lock
        - Configurable calls per time window

    Usage:
        >>> limiter = RateLimiter(max_calls=100, window_seconds=60)
        >>> async with limiter:
        ...     # Make API call
        ...     pass
    """

    def __init__(self, max_calls: int = 100, window_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum calls allowed in window
            window_seconds: Time window in seconds

        Example:
            >>> # Allow 100 calls per minute
            >>> limiter = RateLimiter(max_calls=100, window_seconds=60)
        """
        self.max_calls = max_calls
        self.window = timedelta(seconds=window_seconds)
        self.calls: list[datetime] = []
        self.lock = asyncio.Lock()

    async def __aenter__(self) -> RateLimiter:
        """Acquire rate limit (async context manager)."""
        async with self.lock:
            now = utcnow()

            # Remove old calls outside window
            cutoff = now - self.window
            self.calls = [call_time for call_time in self.calls if call_time > cutoff]

            # If at limit, wait until oldest call expires
            if len(self.calls) >= self.max_calls:
                oldest = self.calls[0]
                wait_until = oldest + self.window
                wait_seconds = (wait_until - now).total_seconds()

                if wait_seconds > 0:
                    await asyncio.sleep(wait_seconds)
                    # Remove expired call
                    self.calls = self.calls[1:]

            # Record this call
            self.calls.append(utcnow())

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit rate limit context."""
        pass


class SteamAPIError(Exception):
    """Base exception for Steam API errors."""
    pass


class SteamAPIRateLimitError(SteamAPIError):
    """Raised when Steam API rate limit is exceeded."""
    pass


class SteamAPINotFoundError(SteamAPIError):
    """Raised when requested resource is not found."""
    pass


class SteamClient:
    """
    Async HTTP client for Steam API operations.

    This client handles all Steam API communication with:
    - Automatic rate limiting
    - Retry logic with exponential backoff
    - Proper error handling and timeouts
    - Connection pooling via httpx

    Design Notes:
        - Uses httpx for async HTTP
        - Rate limiter prevents API abuse
        - Configurable retry attempts
        - All methods are async

    Usage:
        >>> client = SteamClient(api_key="YOUR_KEY")
        >>> await client.start()
        >>> try:
        ...     data = await client.get_app_details(730)
        ... finally:
        ...     await client.close()

        Or use as context manager:
        >>> async with SteamClient(api_key="YOUR_KEY") as client:
        ...     data = await client.get_app_details(730)
    """

    # API endpoints
    STORE_API_BASE = "https://store.steampowered.com/api"
    STEAM_API_BASE = "https://api.steampowered.com"

    def __init__(
        self,
        api_key: str | None = None,
        rate_limit_calls: int = 100,
        rate_limit_window: int = 60,
        max_retries: int = 3,
        timeout_seconds: int = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        """
        Initialize Steam API client.

        Args:
            api_key: Steam Web API key (optional for public endpoints)
            rate_limit_calls: Max calls per window
            rate_limit_window: Rate limit window in seconds
            max_retries: Maximum retry attempts for failed requests
            timeout_seconds: Request timeout in seconds
            transport: Optional httpx transport, used by tests to mock HTTP

        Example:
            >>> client = SteamClient(
            ...     api_key="YOUR_KEY",
            ...     rate_limit_calls=100,
            ...     rate_limit_window=60
            ... )
        """
        self.api_key = api_key
        self.max_retries = max_retries
        self.timeout_seconds = timeout_seconds

        self.rate_limiter = RateLimiter(
            max_calls=rate_limit_calls,
            window_seconds=rate_limit_window
        )

        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """
        Start the client session.

        Creates the httpx async client for connection pooling.
        Must be called before making requests.

        Example:
            >>> client = SteamClient(api_key="YOUR_KEY")
            >>> await client.start()
        """
        if self._client is None:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                headers=headers,
                transport=self._transport,
            )

    async def close(self) -> None:
        """
        Close the client session.

        Cleans up connection pool. Should be called when done.

        Example:
            >>> await client.close()
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> SteamClient:
        """Start session (async context manager)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close session (async context manager)."""
        await self.close()

    async def _request(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        retry_count: int = 0,
    ) -> dict[str, Any]:
        """
        Make HTTP request with rate limiting and retry logic.

        Args:
            url: Full URL to request
            params: Query parameters
            retry_count: Current retry attempt (internal)

        Returns:
            JSON response as dictionary

        Raises:
            SteamAPIError: On API errors
            SteamAPIRateLimitError: On rate limit errors
            SteamAPINotFoundError: On 404 errors

        Example:
            >>> data = await client._request(
            ...     "https://store.steampowered.com/api/appdetails",
            ...     params={"appids": "730"}
            ... )
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        # Apply rate limiting
        async with self.rate_limiter:
            try:
                response = await self._client.get(url, params=params)

                # Handle HTTP errors
                if response.status_code == 404:
                    raise SteamAPINotFoundError(f"Resource not found: {url}")

                if response.status_code == 429:
                    raise SteamAPIRateLimitError("Steam API rate limit exceeded")

                if response.status_code >= 500:
                    # Server error - retry if possible
                    if retry_count < self.max_retries:
                        delay = 2 ** retry_count  # Exponential backoff
                        await asyncio.sleep(delay)
                        return await self._request(url, params, retry_count + 1)

                    raise SteamAPIError(
                        f"Steam API server error: {response.status_code}"
                    )

                if response.status_code != 200:
                    raise SteamAPIError(
                        f"Steam API error: {response.status_code}"
                    )

                payload: dict[str, Any] = response.json()
                return payload

            except httpx.HTTPError as e:
                # Network/connection error - retry if possible
                if retry_count < self.max_retries:
                    delay = 2 ** retry_count
                    await asyncio.sleep(delay)
                    return await self._request(url, params, retry_count + 1)

                raise SteamAPIError(f"Network error: {e}")

    async def get_app_details(self, app_id: int) -> dict[str, Any] | None:
        """
        Get detailed information about a Steam app/game.

        Args:
            app_id: Steam App ID

        Returns:
            App details dictionary (English descriptions), or None if not found

        Raises:
            SteamAPIRateLimitError: On HTTP 429 or an empty (`null`) body

        Example:
            >>> details = await client.get_app_details(730)  # CS:GO
            >>> details["name"]
            'Counter-Strike: Global Offensive'
        """
        url = f"{self.STORE_API_BASE}/appdetails"
        # Pin the language: genre/category descriptions are matched against
        # user exclusions and grouped by name, so they must not localize.
        params = {"appids": str(app_id), "l": "english"}

        try:
            data = await self._request(url, params)

            # A throttled store API sometimes answers HTTP 200 with the body
            # `null`; treat it as the rate limit it is.
            if not isinstance(data, dict):
                raise SteamAPIRateLimitError("Empty appdetails response (throttled)")

            # Steam API returns: {"730": {"success": true, "data": {...}}}
            app_data = data.get(str(app_id))
            if not app_data or not app_data.get("success"):
                return None

            details: dict[str, Any] | None = app_data.get("data")
            return details

        except SteamAPINotFoundError:
            return None

    async def get_owned_games(self, steam_id: str) -> list[dict[str, Any]]:
        """
        Get list of games owned by a Steam user.

        Requires Steam Web API key.

        Args:
            steam_id: Steam ID (64-bit)

        Returns:
            List of owned games with playtime data

        Raises:
            RuntimeError: If API key not configured

        Example:
            >>> games = await client.get_owned_games("76561197960434622")
            >>> len(games)
            150
        """
        if not self.api_key:
            raise RuntimeError("Steam API key required for this endpoint")

        url = f"{self.STEAM_API_BASE}/IPlayerService/GetOwnedGames/v0001/"
        params = {
            "key": self.api_key,
            "steamid": steam_id,
            "include_appinfo": 1,
            "include_played_free_games": 1,
        }

        data = await self._request(url, params)
        response = data.get("response", {})
        games: list[dict[str, Any]] = response.get("games", [])
        return games

    async def get_player_summary(self, steam_id: str) -> dict[str, Any] | None:
        """
        Get Steam player profile information.

        Requires Steam Web API key.

        Args:
            steam_id: Steam ID (64-bit)

        Returns:
            Player profile data, or None if not found

        Raises:
            RuntimeError: If API key not configured

        Example:
            >>> profile = await client.get_player_summary("76561197960434622")
            >>> profile["personaname"]
            'PlayerName'
        """
        if not self.api_key:
            raise RuntimeError("Steam API key required for this endpoint")

        url = f"{self.STEAM_API_BASE}/ISteamUser/GetPlayerSummaries/v0002/"
        params = {
            "key": self.api_key,
            "steamids": steam_id,
        }

        data = await self._request(url, params)
        response = data.get("response", {})
        players = response.get("players", [])

        return players[0] if players else None

    async def get_app_reviews(self, app_id: int) -> dict[str, int] | None:
        """
        Get the review summary of a Steam app.

        Calls ``IUserReviewsService/GetAppReviews`` (public, no key) through
        ``_request``, so the shared rate limiter, the pooled client and its
        retry and error mapping apply. Only ``appid`` and ``num_per_page: 1``
        are sent: the summary is computed by Steam over the API's default
        review population (English reviews by Steam purchasers).

        Args:
            app_id: Steam App ID

        Returns:
            Review data dictionary with keys (a field Steam omits counts as 0):
                - review_score: Steam's summary bucket, 0 (fewer than ten
                  reviews) to 9 (Overwhelmingly Positive)
                - total_positive: Number of positive reviews
                - total_negative: Number of negative reviews
                - total_reviews: Total number of reviews
            or None when Steam answers 200 without a ``query_summary``
            (unknown app, or no reviews to summarise).

        Raises:
            SteamAPIRateLimitError: On HTTP 429
            SteamAPINotFoundError: On HTTP 404
            SteamAPIError: On any other non-200 answer (a redirect included),
                a network or server error that outlives the retries, invalid
                JSON, or a summary field that is not an integer (a boolean,
                a float, Infinity, a string, null) or is out of range
                (negative, a score above 9, a count above
                ``MAX_REVIEW_COUNT``)
        """
        url = f"{self.STEAM_API_BASE}/IUserReviewsService/GetAppReviews/v1/"
        input_json = json.dumps({"appid": app_id, "num_per_page": 1})

        try:
            body: Any = await self._request(url, {"input_json": input_json})
        except ValueError as e:
            raise SteamAPIError("Steam reviews: invalid JSON") from e

        response = body.get("response") if isinstance(body, dict) else None
        summary = response.get("query_summary") if isinstance(response, dict) else None
        if not isinstance(summary, dict):
            logger.warning("review_api_no_data", app_id=app_id)
            return None

        reviews: dict[str, int] = {}
        for key, maximum in REVIEW_SUMMARY_LIMITS.items():
            value = summary.get(key, 0)
            # bool is an int subclass; Steam sends plain JSON integers only.
            if type(value) is not int or not 0 <= value <= maximum:
                raise SteamAPIError(f"Steam reviews: malformed query_summary ({key})")
            reviews[key] = value
        return reviews

    async def search_games(self, query: str, max_results: int = 10) -> list[dict[str, Any]]:
        """
        Search Steam store for games (basic implementation).

        Note: Steam doesn't have an official search API, this uses
        the store API which has limitations. For production use,
        consider using SteamSpy or other third-party APIs.

        Args:
            query: Search query
            max_results: Maximum results to return

        Returns:
            List of matching games

        Example:
            >>> results = await client.search_games("portal", max_results=5)
            >>> results[0]["name"]
            'Portal 2'
        """
        # Note: This is a placeholder. Steam doesn't have a public search API.
        # In production, you'd use SteamSpy or scrape the store page.
        # For now, return empty list.
        return []
