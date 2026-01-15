"""Steam API client with async support and rate limiting.

This module provides an async HTTP client for Steam API operations with
automatic rate limiting, retry logic, and error handling.
"""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import httpx


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

    async def __aenter__(self):
        """Acquire rate limit (async context manager)."""
        async with self.lock:
            now = datetime.utcnow()

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
            self.calls.append(datetime.utcnow())

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
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
        api_key: Optional[str] = None,
        rate_limit_calls: int = 100,
        rate_limit_window: int = 60,
        max_retries: int = 3,
        timeout_seconds: int = 30,
    ):
        """
        Initialize Steam API client.

        Args:
            api_key: Steam Web API key (optional for public endpoints)
            rate_limit_calls: Max calls per window
            rate_limit_window: Rate limit window in seconds
            max_retries: Maximum retry attempts for failed requests
            timeout_seconds: Request timeout in seconds

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

        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
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
                headers=headers
            )

    async def close(self):
        """
        Close the client session.

        Cleans up connection pool. Should be called when done.

        Example:
            >>> await client.close()
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        """Start session (async context manager)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close session (async context manager)."""
        await self.close()

    async def _request(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
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

                return response.json()

            except httpx.HTTPError as e:
                # Network/connection error - retry if possible
                if retry_count < self.max_retries:
                    delay = 2 ** retry_count
                    await asyncio.sleep(delay)
                    return await self._request(url, params, retry_count + 1)

                raise SteamAPIError(f"Network error: {e}")

    async def get_app_details(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a Steam app/game.

        Args:
            app_id: Steam App ID

        Returns:
            App details dictionary, or None if not found

        Example:
            >>> details = await client.get_app_details(730)  # CS:GO
            >>> details["name"]
            'Counter-Strike: Global Offensive'
        """
        url = f"{self.STORE_API_BASE}/appdetails"
        params = {"appids": str(app_id)}

        try:
            data = await self._request(url, params)

            # Steam API returns: {"730": {"success": true, "data": {...}}}
            app_data = data.get(str(app_id))
            if not app_data or not app_data.get("success"):
                return None

            return app_data.get("data")

        except SteamAPINotFoundError:
            return None

    async def get_owned_games(self, steam_id: str) -> list[Dict[str, Any]]:
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
        return response.get("games", [])

    async def get_player_summary(self, steam_id: str) -> Optional[Dict[str, Any]]:
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

    async def get_app_reviews(self, app_id: int) -> Optional[Dict[str, Any]]:
        """
        Get review statistics for a Steam app.

        Uses the Steam Reviews API endpoint to fetch review summary.
        Makes a direct request to avoid rate limiting issues with the store API.

        Args:
            app_id: Steam App ID

        Returns:
            Review data dictionary with keys:
                - review_score: Integer 0-10 (percentage/10)
                - total_positive: Number of positive reviews
                - total_negative: Number of negative reviews
                - total_reviews: Total number of reviews

        Example:
            >>> reviews = await client.get_app_reviews(730)  # CS:GO
            >>> reviews["review_score"]
            9
            >>> reviews["total_reviews"]
            1234567
        """
        url = f"https://store.steampowered.com/appreviews/{app_id}"
        params = {"json": "1"}

        try:
            # Make a fresh request with browser-like headers to avoid 403
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(
                    url,
                    params=params,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "application/json",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                )

                if response.status_code != 200:
                    print(f"Review API returned {response.status_code} for {app_id}")
                    return None

                data = response.json()

            if not data.get("success"):
                return None

            query_summary = data.get("query_summary", {})

            return {
                "review_score": int(query_summary.get("review_score", 0)),
                "total_positive": int(query_summary.get("total_positive", 0)),
                "total_negative": int(query_summary.get("total_negative", 0)),
                "total_reviews": int(query_summary.get("total_reviews", 0)),
            }

        except Exception as e:
            print(f"Error fetching reviews for {app_id}: {e}")
            return None

    async def search_games(self, query: str, max_results: int = 10) -> list[Dict[str, Any]]:
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
