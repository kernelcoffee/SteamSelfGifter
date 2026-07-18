"""SteamGifts scraper client with authentication.

This module provides an async HTTP client for interacting with SteamGifts.com,
including authentication, scraping giveaways, and entering giveaways.
"""

import asyncio
from typing import Any

import httpx
import structlog

from core.exceptions import (
    SteamGiftsError,
    SteamGiftsSessionExpiredError,
)
from utils import steamgifts_parser as parser
from utils.steam_client import RateLimiter

# Re-exported for backwards compatibility; the parsing logic (and these
# word lists) live in utils.steamgifts_parser.
from utils.steamgifts_parser import FORBIDDEN_WORDS, GOOD_WORDS  # noqa: F401

logger = structlog.get_logger()


class SteamGiftsNotFoundError(SteamGiftsError):
    """Raised when requested resource is not found."""

    def __init__(self, message: str):
        super().__init__(message, code="SG_002", details={})


class SteamGiftsUnsafeError(SteamGiftsError):
    """Raised when a giveaway is detected as potentially unsafe/trap."""

    def __init__(self, message: str, safety_score: int = 0):
        super().__init__(message, code="SG_005", details={"safety_score": safety_score})
        self.safety_score = safety_score



class SteamGiftsClient:
    """
    Async HTTP client for SteamGifts.com operations.

    This client handles all SteamGifts.com interactions with:
    - Cookie-based authentication (PHPSESSID)
    - XSRF token management
    - HTML scraping with BeautifulSoup
    - Giveaway listing and filtering
    - Giveaway entry submission
    - User points tracking

    Design Notes:
        - Uses httpx for async HTTP
        - Requires valid PHPSESSID cookie for authentication
        - XSRF token extracted from pages and used for POST requests
        - BeautifulSoup for HTML parsing
        - All methods are async

    Usage:
        >>> client = SteamGiftsClient(
        ...     phpsessid="your_session_id",
        ...     user_agent="YourBot/1.0"
        ... )
        >>> await client.start()
        >>> try:
        ...     points = await client.get_user_points()
        ...     giveaways = await client.get_giveaways()
        ... finally:
        ...     await client.close()

        Or use as context manager:
        >>> async with SteamGiftsClient(phpsessid="...", user_agent="...") as client:
        ...     points = await client.get_user_points()
    """

    BASE_URL = "https://www.steamgifts.com"

    def __init__(
        self,
        phpsessid: str,
        user_agent: str,
        xsrf_token: str | None = None,
        timeout_seconds: int = 30,
        rate_limit_calls: int = 30,
        rate_limit_window: int = 60,
        max_retries: int = 3,
    ):
        """
        Initialize SteamGifts client.

        Args:
            phpsessid: PHPSESSID cookie value for authentication
            user_agent: User-Agent header to use
            xsrf_token: XSRF token (if known), otherwise will be extracted
            timeout_seconds: Request timeout in seconds
            rate_limit_calls: Max requests per rate-limit window
            rate_limit_window: Rate-limit window in seconds
            max_retries: Retry attempts for transient failures

        Example:
            >>> client = SteamGiftsClient(
            ...     phpsessid="abc123...",
            ...     user_agent="SteamSelfGifter/2.0"
            ... )
        """
        self.phpsessid = phpsessid
        self.user_agent = user_agent
        self.xsrf_token = xsrf_token
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        self.rate_limiter = RateLimiter(
            max_calls=rate_limit_calls,
            window_seconds=rate_limit_window,
        )

        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        """
        Start the client session.

        Creates the httpx async client with cookies and headers.
        Must be called before making requests.

        Example:
            >>> client = SteamGiftsClient(phpsessid="...", user_agent="...")
            >>> await client.start()
        """
        if self._client is None:
            cookies = {"PHPSESSID": self.phpsessid} if self.phpsessid else {}
            headers = {"User-Agent": self.user_agent}

            self._client = httpx.AsyncClient(
                timeout=self.timeout_seconds,
                cookies=cookies,
                headers=headers,
                follow_redirects=True,
            )

            # Extract XSRF token if not provided (only if we have a session)
            if not self.xsrf_token and self.phpsessid:
                await self._refresh_xsrf_token()

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

    async def __aenter__(self) -> SteamGiftsClient:
        """Start session (async context manager)."""
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close session (async context manager)."""
        await self.close()

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        """Rate-limited GET with retry/backoff for transient failures.

        Retries on transport errors, 5xx responses and 429 (honoring a numeric
        Retry-After header when present).
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        attempt = 0
        while True:
            async with self.rate_limiter:
                try:
                    response = await self._client.get(url, **kwargs)
                except httpx.TransportError as e:
                    if attempt >= self.max_retries:
                        raise SteamGiftsError(
                            f"Request failed after {attempt + 1} attempts: {e}",
                            code="SG_002",
                            details={"url": url},
                        ) from e
                    delay = min(2.0**attempt, 30.0)
                    logger.warning(
                        "steamgifts_request_retry",
                        url=url, attempt=attempt + 1, delay=delay, error=str(e),
                    )
                    await asyncio.sleep(delay)
                    attempt += 1
                    continue

            if response.status_code == 429 or response.status_code >= 500:
                if attempt >= self.max_retries:
                    return response  # let the caller's status handling report it
                delay = min(2.0**attempt, 30.0)
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        delay = min(float(retry_after), 60.0)
                logger.warning(
                    "steamgifts_request_retry",
                    url=url, attempt=attempt + 1, delay=delay,
                    status_code=response.status_code,
                )
                await asyncio.sleep(delay)
                attempt += 1
                continue

            return response

    async def _post(self, url: str, **kwargs: Any) -> httpx.Response:
        """Rate-limited POST, retried only on connect errors.

        POSTs mutate state on SteamGifts (enter/hide/comment), so a request
        that may have reached the server is never replayed; only failures to
        connect at all are retried.
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        attempt = 0
        while True:
            async with self.rate_limiter:
                try:
                    return await self._client.post(url, **kwargs)
                except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                    if attempt >= self.max_retries:
                        raise SteamGiftsError(
                            f"Request failed after {attempt + 1} attempts: {e}",
                            code="SG_002",
                            details={"url": url},
                        ) from e
                    delay = min(2.0**attempt, 30.0)
                    logger.warning(
                        "steamgifts_request_retry",
                        url=url, attempt=attempt + 1, delay=delay, error=str(e),
                    )
                    await asyncio.sleep(delay)
                    attempt += 1

    async def _refresh_xsrf_token(self) -> None:
        """
        Refresh XSRF token by fetching homepage.

        The XSRF token is required for POST requests and is embedded
        in the HTML of any authenticated page.

        Raises:
            SteamGiftsAuthError: If token cannot be extracted (not authenticated)
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        response = await self._get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch homepage: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        token = parser.extract_xsrf_token(response.text)
        if token is None:
            raise SteamGiftsSessionExpiredError(
                "Could not extract XSRF token - session expired or invalid",
                code="SG_004",
                details={"reason": "xsrf_token_not_found"},
            )
        self.xsrf_token = token

    async def get_user_points(self) -> int:
        """
        Get current user's points balance.

        Returns:
            Current points balance

        Raises:
            SteamGiftsAuthError: If not authenticated

        Example:
            >>> points = await client.get_user_points()
            >>> print(f"You have {points} points")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        response = await self._get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch points: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        try:
            points = parser.parse_user_points(response.text)
        except ValueError as e:
            raise SteamGiftsError(str(e), code="SG_002", details={})

        if points is None:
            raise SteamGiftsSessionExpiredError(
                "Could not find points - session expired or invalid",
                code="SG_004",
                details={"reason": "points_element_not_found"},
            )

        return points

    async def get_user_info(self) -> dict[str, Any]:
        """
        Get current user's info (username and points).

        Returns:
            Dictionary with 'username' and 'points' keys

        Raises:
            SteamGiftsAuthError: If not authenticated

        Example:
            >>> info = await client.get_user_info()
            >>> print(f"Hello {info['username']}, you have {info['points']} points")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        response = await self._get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch user info: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        try:
            points = parser.parse_user_points(response.text)
        except ValueError as e:
            raise SteamGiftsError(str(e), code="SG_002", details={})

        if points is None:
            raise SteamGiftsSessionExpiredError(
                "Could not find points - session expired or invalid",
                code="SG_004",
                details={"reason": "points_element_not_found"},
            )

        username = parser.parse_username(response.text)
        if not username:
            raise SteamGiftsSessionExpiredError(
                "Could not find username - session expired or invalid",
                code="SG_004",
                details={"reason": "username_not_found"},
            )

        return {
            "username": username,
            "points": points,
        }

    async def get_giveaways(
        self,
        page: int = 1,
        search_query: str | None = None,
        giveaway_type: str | None = None,
        dlc_only: bool = False,
        min_copies: int | None = None,
    ) -> list[dict[str, Any]]:
        """
        Get list of giveaways from SteamGifts.

        Args:
            page: Page number (default: 1)
            search_query: Optional search query to filter giveaways
            giveaway_type: Optional type filter. Supported values:
                - "wishlist": Games on your Steam wishlist
                - "recommended": Recommended games
                - "new": New giveaways
                - "group": Group giveaways
                - None: All giveaways (default)
            dlc_only: If True, only fetch DLC giveaways
            min_copies: Minimum number of copies (e.g., 2 for multi-copy)

        Returns:
            List of giveaway dictionaries with keys:
                - code: Giveaway code (e.g., "AbCd1")
                - game_name: Name of the game
                - price: Points required to enter
                - copies: Number of copies
                - entries: Number of entries
                - end_time: When giveaway ends (datetime)
                - thumbnail_url: Game thumbnail URL
                - game_id: Steam App ID (if available)
                - is_wishlist: True if this is from a wishlist scan

        Example:
            >>> giveaways = await client.get_giveaways(page=1)
            >>> for ga in giveaways:
            ...     print(f"{ga['game_name']}: {ga['price']}P")

            >>> # Get wishlist giveaways
            >>> wishlist = await client.get_giveaways(giveaway_type="wishlist")

            >>> # Get DLC giveaways
            >>> dlcs = await client.get_giveaways(dlc_only=True)
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaways/search"
        params: dict[str, str | int] = {"page": page}

        if search_query:
            params["q"] = search_query

        if giveaway_type:
            params["type"] = giveaway_type

        if dlc_only:
            params["dlc"] = "true"

        if min_copies:
            params["copy_min"] = str(min_copies)

        response = await self._get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        return parser.parse_giveaway_list(
            response.text, mark_wishlist=giveaway_type == "wishlist"
        )

    async def enter_giveaway(self, giveaway_code: str) -> bool:
        """
        Enter a giveaway.

        Args:
            giveaway_code: Giveaway code (e.g., "AbCd1")

        Returns:
            True if entry was successful, False otherwise

        Raises:
            SteamGiftsAuthError: If not authenticated
            SteamGiftsError: On other errors

        Example:
            >>> success = await client.enter_giveaway("AbCd1")
            >>> if success:
            ...     print("Successfully entered!")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        if not self.xsrf_token:
            await self._refresh_xsrf_token()

        url = f"{self.BASE_URL}/ajax.php"
        data = {
            "xsrf_token": self.xsrf_token,
            "do": "entry_insert",
            "code": giveaway_code,
        }

        response = await self._post(url, data=data)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to enter giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        # Parse JSON response
        try:
            result = response.json()

            # SteamGifts returns {"type": "success"} on success
            if result.get("type") == "success":
                return True

            # If type is "error", there's usually a message
            error_msg = result.get("msg", "Unknown error")
            logger.warning("giveaway_entry_rejected", error=error_msg)
            return False

        except Exception as e:
            raise SteamGiftsError(
                f"Error parsing response: {e}",
                code="SG_002",
                details={"error": str(e)},
            )

    async def get_giveaway_details(self, giveaway_code: str) -> dict[str, Any]:
        """
        Get detailed information about a specific giveaway.

        Args:
            giveaway_code: Giveaway code (e.g., "AbCd1")

        Returns:
            Dictionary with detailed giveaway data

        Raises:
            SteamGiftsNotFoundError: If giveaway not found

        Example:
            >>> details = await client.get_giveaway_details("AbCd1")
            >>> print(f"Game: {details['game_name']}")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaway/{giveaway_code}/"
        response = await self._get(url)

        if response.status_code == 404:
            raise SteamGiftsNotFoundError(f"Giveaway not found: {giveaway_code}")

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        details = parser.parse_giveaway_details(response.text)
        return {"code": giveaway_code, **details}

    async def check_if_entered(self, giveaway_code: str) -> bool:
        """
        Check if user has already entered a giveaway.

        Args:
            giveaway_code: Giveaway code to check

        Returns:
            True if already entered, False otherwise

        Example:
            >>> if await client.check_if_entered("AbCd1"):
            ...     print("Already entered this giveaway")
        """
        # This would require checking the giveaway page for entry indicators
        # For now, return False as placeholder
        # Real implementation would scrape the giveaway page
        return False

    async def get_won_giveaways(self, page: int = 1) -> list[dict[str, Any]]:
        """
        Get list of won giveaways from SteamGifts.

        Scrapes the /giveaways/won page to find giveaways the user has won.

        Args:
            page: Page number (default: 1)

        Returns:
            List of won giveaway dictionaries with keys:
                - code: Giveaway code (e.g., "AbCd1")
                - game_name: Name of the game
                - game_id: Steam App ID (if available)
                - won_at: When the giveaway ended (datetime)
                - received: Whether the gift has been received/marked
                - steam_key: Steam key if visible (usually not shown)

        Example:
            >>> wins = await client.get_won_giveaways()
            >>> for win in wins:
            ...     print(f"Won: {win['game_name']}")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaways/won"
        params: dict[str, str | int] = {"page": page}

        response = await self._get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch won giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        return parser.parse_won_giveaways(response.text)

    async def get_entered_giveaways(self, page: int = 1) -> list[dict[str, Any]]:
        """
        Get list of entered giveaways from SteamGifts.

        Scrapes the /giveaways/entered page to find giveaways the user has entered.

        Args:
            page: Page number (default: 1)

        Returns:
            List of entered giveaway dictionaries with keys:
                - code: Giveaway code (e.g., "AbCd1")
                - game_name: Name of the game
                - game_id: Steam App ID (if available)
                - price: Points spent to enter
                - entries: Current number of entries
                - end_time: When the giveaway ends (datetime)
                - entered_at: When user entered (datetime)

        Example:
            >>> entered = await client.get_entered_giveaways()
            >>> for ga in entered:
            ...     print(f"Entered: {ga['game_name']} ({ga['code']})")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaways/entered"
        params: dict[str, str | int] = {"page": page}

        response = await self._get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch entered giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        return parser.parse_entered_giveaways(response.text)

    def check_page_safety(self, html_content: str) -> dict[str, Any]:
        """Analyze giveaway page text for trap indicators.

        Thin wrapper around :func:`utils.steamgifts_parser.check_page_safety`
        (see it for the result shape).
        """
        return parser.check_page_safety(html_content)

    async def check_giveaway_safety(self, giveaway_code: str) -> dict[str, Any]:
        """
        Check if a specific giveaway is safe to enter.

        Fetches the giveaway page and analyzes it for trap indicators.

        Args:
            giveaway_code: Giveaway code to check

        Returns:
            Dictionary with safety results (see check_page_safety)

        Raises:
            SteamGiftsNotFoundError: If giveaway not found

        Example:
            >>> safety = await client.check_giveaway_safety("AbCd1")
            >>> if safety['is_safe']:
            ...     await client.enter_giveaway("AbCd1")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaway/{giveaway_code}/"
        response = await self._get(url)

        if response.status_code == 404:
            raise SteamGiftsNotFoundError(f"Giveaway not found: {giveaway_code}")

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        return self.check_page_safety(response.text)

    async def hide_giveaway(self, game_id: int) -> bool:
        """
        Hide all giveaways for a specific game.

        This hides the game so it won't appear in future giveaway lists.
        Useful for hiding games you don't want or potential traps.

        Args:
            game_id: Steam game ID to hide

        Returns:
            True if hide was successful, False otherwise

        Raises:
            SteamGiftsAuthError: If not authenticated

        Example:
            >>> success = await client.hide_giveaway(12345)
            >>> if success:
            ...     print("Game hidden successfully")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        if not self.xsrf_token:
            await self._refresh_xsrf_token()

        url = f"{self.BASE_URL}/ajax.php"
        data = {
            "xsrf_token": self.xsrf_token,
            "game_id": game_id,
            "do": "hide_giveaways_by_game_id",
        }

        response = await self._post(url, data=data)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to hide giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        # SteamGifts returns empty response on success
        return response.status_code == 200

    async def get_giveaway_game_id(self, giveaway_code: str) -> int | None:
        """
        Get the Steam game ID for a giveaway.

        Fetches the giveaway page and extracts the game ID from the
        data-game-id attribute.

        Args:
            giveaway_code: Giveaway code

        Returns:
            Steam game ID, or None if not found

        Example:
            >>> game_id = await client.get_giveaway_game_id("AbCd1")
            >>> if game_id:
            ...     await client.hide_giveaway(game_id)
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        url = f"{self.BASE_URL}/giveaway/{giveaway_code}/"
        response = await self._get(url)

        if response.status_code != 200:
            return None

        return parser.parse_giveaway_game_id(response.text)

    async def post_comment(
        self, giveaway_code: str, comment_text: str = "Thanks!"
    ) -> bool:
        """
        Post a comment on a giveaway.

        Args:
            giveaway_code: Giveaway code (e.g., "AbCd1")
            comment_text: Comment text to post (default: "Thanks!")

        Returns:
            True if comment was posted successfully, False otherwise

        Raises:
            SteamGiftsError: On errors

        Example:
            >>> success = await client.post_comment("AbCd1", "Thanks for the giveaway!")
            >>> if success:
            ...     print("Comment posted!")
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        if not self.xsrf_token:
            await self._refresh_xsrf_token()

        url = f"{self.BASE_URL}/giveaway/{giveaway_code}/"
        data = {
            "xsrf_token": self.xsrf_token,
            "description": comment_text,
            "do": "comment_new",
            "parent_id": "",
        }

        response = await self._post(url, data=data)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to post comment: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        # SteamGifts returns HTML with the comment on success
        # A successful post will contain the comment text in the response
        return comment_text in response.text
