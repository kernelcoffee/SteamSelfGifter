"""SteamGifts scraper client with authentication.

This module provides an async HTTP client for interacting with SteamGifts.com,
including authentication, scraping giveaways, and entering giveaways.
"""

import re
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx
from bs4 import BeautifulSoup

from core.exceptions import (
    SteamGiftsError,
    SteamGiftsSessionExpiredError,
    SteamGiftsNotConfiguredError,
)


class SteamGiftsNotFoundError(SteamGiftsError):
    """Raised when requested resource is not found."""

    def __init__(self, message: str):
        super().__init__(message, code="SG_002", details={})


class SteamGiftsUnsafeError(SteamGiftsError):
    """Raised when a giveaway is detected as potentially unsafe/trap."""

    def __init__(self, message: str, safety_score: int = 0):
        super().__init__(message, code="SG_005", details={"safety_score": safety_score})
        self.safety_score = safety_score


# Safety detection word lists (from legacy code)
# Words that indicate potential traps/scams
FORBIDDEN_WORDS = (" ban", " fake", " bot", " not enter", " don't enter", " do not enter")
# Words that look similar but are innocent (to avoid false positives)
GOOD_WORDS = (" bank", " banan", " both", " band", " banner", " bang")


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
        xsrf_token: Optional[str] = None,
        timeout_seconds: int = 30,
    ):
        """
        Initialize SteamGifts client.

        Args:
            phpsessid: PHPSESSID cookie value for authentication
            user_agent: User-Agent header to use
            xsrf_token: XSRF token (if known), otherwise will be extracted
            timeout_seconds: Request timeout in seconds

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

        self._client: Optional[httpx.AsyncClient] = None

    async def start(self):
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

    async def _refresh_xsrf_token(self):
        """
        Refresh XSRF token by fetching homepage.

        The XSRF token is required for POST requests and is embedded
        in the HTML of any authenticated page.

        Raises:
            SteamGiftsAuthError: If token cannot be extracted (not authenticated)
        """
        if self._client is None:
            raise RuntimeError("Client session not started. Call start() first.")

        response = await self._client.get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch homepage: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # XSRF token is in a hidden input or data attribute
        token_input = soup.find("input", {"name": "xsrf_token"})
        if token_input:
            self.xsrf_token = token_input.get("value")
            return

        # Try to find it in data-form attribute
        form_element = soup.find(attrs={"data-form": True})
        if form_element:
            # Token might be in a JSON-encoded string
            import json
            try:
                form_data = json.loads(form_element["data-form"])
                if "xsrf_token" in form_data:
                    self.xsrf_token = form_data["xsrf_token"]
                    return
            except (json.JSONDecodeError, KeyError):
                pass

        raise SteamGiftsSessionExpiredError(
            "Could not extract XSRF token - session expired or invalid",
            code="SG_004",
            details={"reason": "xsrf_token_not_found"},
        )

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

        response = await self._client.get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch points: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # Points are in nav__points element
        points_element = soup.find("span", class_="nav__points")
        if not points_element:
            raise SteamGiftsSessionExpiredError(
                "Could not find points - session expired or invalid",
                code="SG_004",
                details={"reason": "points_element_not_found"},
            )

        # Extract number from text like "123P"
        points_text = points_element.text.strip()
        match = re.search(r"(\d+)", points_text)
        if not match:
            raise SteamGiftsError(
                f"Could not parse points: {points_text}",
                code="SG_002",
                details={"points_text": points_text},
            )

        return int(match.group(1))

    async def get_user_info(self) -> Dict[str, Any]:
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

        response = await self._client.get(self.BASE_URL)

        if response.status_code != 200:
            raise SteamGiftsSessionExpiredError(
                f"Failed to fetch user info: {response.status_code}",
                code="SG_004",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # Points are in nav__points element
        points_element = soup.find("span", class_="nav__points")
        if not points_element:
            raise SteamGiftsSessionExpiredError(
                "Could not find points - session expired or invalid",
                code="SG_004",
                details={"reason": "points_element_not_found"},
            )

        # Extract number from text
        points_text = points_element.text.strip()
        match = re.search(r"(\d+)", points_text)
        if not match:
            raise SteamGiftsError(
                f"Could not parse points: {points_text}",
                code="SG_002",
                details={"points_text": points_text},
            )
        points = int(match.group(1))

        # Username is in a link to /user/<username>
        # The logged-in user's profile link is typically in the nav area
        username = None

        # Method 1: Look for nav__avatar-inner-wrap (user avatar link)
        avatar_link = soup.find("a", class_="nav__avatar-inner-wrap")
        if avatar_link:
            href = avatar_link.get("href", "")
            username_match = re.search(r"/user/([^/]+)", href)
            if username_match:
                username = username_match.group(1)

        # Method 2: Look for the user's profile link in the nav area
        # This is typically the first /user/ link that appears in navigation
        if not username:
            # Find nav__button-container which contains the user dropdown
            nav_container = soup.find("div", class_="nav__button-container")
            if nav_container:
                user_link = nav_container.find("a", href=re.compile(r"^/user/"))
                if user_link:
                    href = user_link.get("href", "")
                    username_match = re.search(r"/user/([^/]+)", href)
                    if username_match:
                        username = username_match.group(1)

        # Method 3: Look for any /user/ link in the header/nav that points to current user
        # The logged-in user's link is usually near the top and associated with points
        if not username:
            # Find the nav__points element's parent and look for nearby user link
            if points_element:
                parent = points_element.parent
                while parent and parent.name != "nav":
                    user_link = parent.find("a", href=re.compile(r"^/user/"))
                    if user_link:
                        href = user_link.get("href", "")
                        username_match = re.search(r"/user/([^/]+)", href)
                        if username_match:
                            username = username_match.group(1)
                            break
                    parent = parent.parent

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
        search_query: Optional[str] = None,
        giveaway_type: Optional[str] = None,
        dlc_only: bool = False,
        min_copies: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
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
        params = {"page": page}

        if search_query:
            params["q"] = search_query

        if giveaway_type:
            params["type"] = giveaway_type

        if dlc_only:
            params["dlc"] = "true"

        if min_copies:
            params["copy_min"] = str(min_copies)

        response = await self._client.get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        giveaways = []
        giveaway_elements = soup.find_all("div", class_="giveaway__row-inner-wrap")

        for element in giveaway_elements:
            try:
                # Skip pinned/advertisement giveaways (they appear at the top of
                # wishlist pages inside a pinned-giveaways__inner-wrap container)
                if element.find_parent("div", class_="pinned-giveaways__inner-wrap"):
                    continue

                giveaway = self._parse_giveaway_element(element)
                if giveaway:
                    # Mark wishlist giveaways
                    giveaway["is_wishlist"] = giveaway_type == "wishlist"
                    giveaways.append(giveaway)
            except Exception as e:
                # Log error but continue parsing other giveaways
                print(f"Error parsing giveaway: {e}")
                continue

        return giveaways

    def _parse_giveaway_element(self, element) -> Optional[Dict[str, Any]]:
        """
        Parse giveaway data from HTML element.

        Args:
            element: BeautifulSoup element containing giveaway data

        Returns:
            Dictionary with giveaway data, or None if parsing fails
        """
        # Extract giveaway code from link
        link = element.find("a", class_="giveaway__heading__name")
        if not link:
            return None

        href = link.get("href", "")
        code_match = re.search(r"/giveaway/([^/]+)/", href)
        if not code_match:
            return None

        code = code_match.group(1)
        game_name = link.text.strip()

        # Extract points
        points_element = element.find("span", class_="giveaway__heading__thin")
        price = 0
        if points_element:
            points_text = points_element.text.strip()
            match = re.search(r"\((\d+)P\)", points_text)
            if match:
                price = int(match.group(1))

        # Extract copies
        copies = 1
        copies_element = element.find("span", class_="giveaway__heading__thin")
        if copies_element:
            copies_text = copies_element.text.strip()
            match = re.search(r"(\d+)\s+Copies", copies_text)
            if match:
                copies = int(match.group(1))

        # Extract entries count
        entries = 0
        entries_element = element.find("span", class_="giveaway__links")
        if entries_element:
            entries_text = entries_element.text.strip()
            match = re.search(r"(\d+)\s+entries", entries_text)
            if match:
                entries = int(match.group(1))

        # Extract end time
        time_element = element.find("span", {"data-timestamp": True})
        end_time = None
        if time_element:
            timestamp = int(time_element["data-timestamp"])
            end_time = datetime.fromtimestamp(timestamp)

        # Extract thumbnail URL
        thumbnail_url = None
        img_element = element.find("a", class_="giveaway_image_thumbnail")
        if img_element:
            style = img_element.get("style", "")
            url_match = re.search(r"url\((.*?)\)", style)
            if url_match:
                thumbnail_url = url_match.group(1).strip("'\"")

        # Try to extract game ID from thumbnail URL
        game_id = None
        if thumbnail_url:
            id_match = re.search(r"/apps/(\d+)/", thumbnail_url)
            if id_match:
                game_id = int(id_match.group(1))

        # Check if already entered (has "is-faded" class)
        is_entered = "is-faded" in element.get("class", [])

        return {
            "code": code,
            "game_name": game_name,
            "price": price,
            "copies": copies,
            "entries": entries,
            "end_time": end_time,
            "thumbnail_url": thumbnail_url,
            "game_id": game_id,
            "is_entered": is_entered,
        }

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

        response = await self._client.post(url, data=data)

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
            print(f"Failed to enter giveaway: {error_msg}")
            return False

        except Exception as e:
            raise SteamGiftsError(
                f"Error parsing response: {e}",
                code="SG_002",
                details={"error": str(e)},
            )

    async def get_giveaway_details(self, giveaway_code: str) -> Dict[str, Any]:
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
        response = await self._client.get(url)

        if response.status_code == 404:
            raise SteamGiftsNotFoundError(f"Giveaway not found: {giveaway_code}")

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        # Parse giveaway details from page
        # This is a simplified version - real implementation would extract more details
        heading = soup.find("a", class_="giveaway__heading__name")
        game_name = heading.text.strip() if heading else "Unknown"

        return {
            "code": giveaway_code,
            "game_name": game_name,
            # Add more fields as needed
        }

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

    async def get_won_giveaways(self, page: int = 1) -> List[Dict[str, Any]]:
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
        params = {"page": page}

        response = await self._client.get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch won giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        won_giveaways = []

        # Won giveaways are in table rows
        table_rows = soup.find_all("div", class_="table__row-inner-wrap")

        for row in table_rows:
            try:
                won = self._parse_won_giveaway_row(row)
                if won:
                    won_giveaways.append(won)
            except Exception as e:
                print(f"Error parsing won giveaway: {e}")
                continue

        return won_giveaways

    def _parse_won_giveaway_row(self, row) -> Optional[Dict[str, Any]]:
        """
        Parse a won giveaway row from the /giveaways/won page.

        Args:
            row: BeautifulSoup element containing won giveaway data

        Returns:
            Dictionary with won giveaway data, or None if parsing fails
        """
        # Find the game name and giveaway link
        heading = row.find("a", class_="table__column__heading")
        if not heading:
            return None

        game_name = heading.text.strip()
        href = heading.get("href", "")

        # Extract giveaway code from URL
        code_match = re.search(r"/giveaway/([^/]+)/", href)
        if not code_match:
            return None

        code = code_match.group(1)

        # Try to extract game ID from thumbnail image URL
        game_id = None
        thumbnail = row.find("a", class_="table_image_thumbnail")
        if thumbnail:
            style = thumbnail.get("style", "")
            id_match = re.search(r"/apps/(\d+)/", style)
            if id_match:
                game_id = int(id_match.group(1))

        # Check if gift was received (look for icon-green class in feedback div)
        received = False
        feedback_divs = row.find_all("div", class_="table__column--gift-feedback")
        for feedback in feedback_divs:
            if feedback.find("i", class_="icon-green"):
                received = True
                break

        # Try to get the end time from timestamp
        won_at = None
        time_element = row.find("span", {"data-timestamp": True})
        if time_element:
            try:
                timestamp = int(time_element["data-timestamp"])
                won_at = datetime.fromtimestamp(timestamp)
            except (ValueError, KeyError):
                pass

        # Extract Steam key if visible
        steam_key = None
        key_element = row.find("i", {"data-clipboard-text": True})
        if key_element:
            steam_key = key_element.get("data-clipboard-text")

        return {
            "code": code,
            "game_name": game_name,
            "game_id": game_id,
            "won_at": won_at,
            "received": received,
            "steam_key": steam_key,
        }

    async def get_entered_giveaways(self, page: int = 1) -> List[Dict[str, Any]]:
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
        params = {"page": page}

        response = await self._client.get(url, params=params)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to fetch entered giveaways: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        soup = BeautifulSoup(response.text, "html.parser")

        entered_giveaways = []

        # Entered giveaways are in table rows
        table_rows = soup.find_all("div", class_="table__row-inner-wrap")

        for row in table_rows:
            try:
                entered = self._parse_entered_giveaway_row(row)
                if entered:
                    entered_giveaways.append(entered)
            except Exception as e:
                print(f"Error parsing entered giveaway: {e}")
                continue

        return entered_giveaways

    def _parse_entered_giveaway_row(self, row) -> Optional[Dict[str, Any]]:
        """
        Parse an entered giveaway row from the /giveaways/entered page.

        Args:
            row: BeautifulSoup element containing entered giveaway data

        Returns:
            Dictionary with entered giveaway data, or None if parsing fails
        """
        # Find the game name and giveaway link
        heading = row.find("a", class_="table__column__heading")
        if not heading:
            return None

        # Game name is the text without the price span
        game_name_parts = []
        for child in heading.children:
            if isinstance(child, str):
                game_name_parts.append(child.strip())
            elif child.name != "span":
                game_name_parts.append(child.text.strip())
        game_name = " ".join(game_name_parts).strip()

        href = heading.get("href", "")

        # Extract giveaway code from URL
        code_match = re.search(r"/giveaway/([^/]+)/", href)
        if not code_match:
            return None

        code = code_match.group(1)

        # Extract price from the span inside heading
        price = 0
        price_span = heading.find("span", class_="is-faded")
        if price_span:
            price_match = re.search(r"\((\d+)P\)", price_span.text)
            if price_match:
                price = int(price_match.group(1))

        # Try to extract game ID from thumbnail image URL
        game_id = None
        thumbnail = row.find("a", class_="table_image_thumbnail")
        if thumbnail:
            style = thumbnail.get("style", "")
            id_match = re.search(r"/apps/(\d+)/", style)
            if id_match:
                game_id = int(id_match.group(1))

        # Get entries count (usually in a text-center column)
        entries = 0
        columns = row.find_all("div", class_="table__column--width-small")
        if columns:
            # First column is usually entries count
            entries_text = columns[0].text.strip().replace(",", "")
            if entries_text.isdigit():
                entries = int(entries_text)

        # Get end time from the "remaining" text
        end_time = None
        # Look for timestamp in the fill column
        fill_col = row.find("div", class_="table__column--width-fill")
        if fill_col:
            time_element = fill_col.find("span", {"data-timestamp": True})
            if time_element:
                try:
                    timestamp = int(time_element["data-timestamp"])
                    end_time = datetime.fromtimestamp(timestamp)
                except (ValueError, KeyError):
                    pass

        # Get entered_at timestamp (second timestamp in the row)
        entered_at = None
        if len(columns) >= 2:
            time_element = columns[1].find("span", {"data-timestamp": True})
            if time_element:
                try:
                    timestamp = int(time_element["data-timestamp"])
                    entered_at = datetime.fromtimestamp(timestamp)
                except (ValueError, KeyError):
                    pass

        return {
            "code": code,
            "game_name": game_name,
            "game_id": game_id,
            "price": price,
            "entries": entries,
            "end_time": end_time,
            "entered_at": entered_at,
        }

    def check_page_safety(self, html_content: str) -> Dict[str, Any]:
        """
        Check if a giveaway page contains suspicious content.

        Analyzes the page text for forbidden words that might indicate
        a trap giveaway (e.g., "don't enter", "ban", "fake").

        Args:
            html_content: Raw HTML content of the giveaway page

        Returns:
            Dictionary with safety check results:
                - is_safe: True if page appears safe
                - safety_score: Score from 0-100 (higher = safer)
                - bad_count: Number of bad words found
                - good_count: Number of good words found (false positives)
                - details: List of found bad words

        Example:
            >>> result = client.check_page_safety(html)
            >>> if not result['is_safe']:
            ...     print(f"Warning: {result['details']}")
        """
        text_lower = html_content.lower()

        bad_count = 0
        good_count = 0
        found_bad_words = []

        # Count forbidden words
        for bad_word in FORBIDDEN_WORDS:
            count = text_lower.count(bad_word.lower())
            if count > 0:
                bad_count += count
                found_bad_words.append(bad_word.strip())

        # Count good words (false positive indicators)
        if bad_count > 0:
            for good_word in GOOD_WORDS:
                good_count += text_lower.count(good_word.lower())

        # Calculate safety score
        # Net bad = bad words minus false positives
        net_bad = max(0, bad_count - good_count)

        if net_bad == 0:
            safety_score = 100
            is_safe = True
        elif net_bad <= 2:
            safety_score = 50
            is_safe = True  # Borderline, but allow
        else:
            safety_score = max(0, 100 - (net_bad * 20))
            is_safe = False

        return {
            "is_safe": is_safe,
            "safety_score": safety_score,
            "bad_count": bad_count,
            "good_count": good_count,
            "net_bad": net_bad,
            "details": found_bad_words,
        }

    async def check_giveaway_safety(self, giveaway_code: str) -> Dict[str, Any]:
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
        response = await self._client.get(url)

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

        response = await self._client.post(url, data=data)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to hide giveaway: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        # SteamGifts returns empty response on success
        return response.status_code == 200

    async def get_giveaway_game_id(self, giveaway_code: str) -> Optional[int]:
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
        response = await self._client.get(url)

        if response.status_code != 200:
            return None

        soup = BeautifulSoup(response.text, "html.parser")

        # Game ID is in data-game-id attribute of the featured wrapper
        featured = soup.find("div", class_="featured__outer-wrap")
        if featured:
            game_id = featured.get("data-game-id")
            if game_id:
                return int(game_id)

        return None

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

        response = await self._client.post(url, data=data)

        if response.status_code != 200:
            raise SteamGiftsError(
                f"Failed to post comment: {response.status_code}",
                code="SG_002",
                details={"status_code": response.status_code},
            )

        # SteamGifts returns HTML with the comment on success
        # A successful post will contain the comment text in the response
        return comment_text in response.text
