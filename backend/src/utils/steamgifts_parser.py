"""Pure HTML parsers for SteamGifts pages.

Every function here takes HTML (or a BeautifulSoup element) and returns plain
data — no HTTP, no sessions, no app exceptions. This keeps the scraping logic
testable against saved page fixtures (see tests/unit/test_steamgifts_parser.py
and tests/fixtures/), so a SteamGifts markup change shows up as a failing
fixture test instead of silently wrong data.

Error convention: "not found" is ``None`` (or an empty list); genuinely
malformed content raises ``ValueError``. The HTTP client maps those onto its
session/scrape exceptions.
"""

import json
import re
from typing import Any

import structlog
from bs4 import BeautifulSoup

from core.time import from_timestamp

logger = structlog.get_logger()

# Safety detection word lists (from legacy code)
# Words that indicate potential traps/scams
FORBIDDEN_WORDS = (" ban", " fake", " bot", " not enter", " don't enter", " do not enter")
# Words that look similar but are innocent (to avoid false positives)
GOOD_WORDS = (" bank", " banan", " both", " band", " banner", " bang")


def has_no_results_marker(html: str) -> bool:
    """True when the page explicitly says the search matched nothing.

    SteamGifts renders ``<div class="pagination pagination--no-results">``
    ("No results were found.") on legitimately empty result pages. Zero parsed
    giveaways WITHOUT this marker means the markup has likely changed and the
    scraper is broken (scrape drift), not that the list is empty.
    """
    return "pagination--no-results" in html


def extract_xsrf_token(html: str) -> str | None:
    """Extract the XSRF token embedded in any authenticated page, or None."""
    soup = BeautifulSoup(html, "html.parser")

    # XSRF token is in a hidden input or data attribute
    token_input = soup.find("input", {"name": "xsrf_token"})
    if token_input:
        value = token_input.get("value")
        return str(value) if value else None

    # Try to find it in data-form attribute (JSON-encoded)
    form_element = soup.find(lambda tag: tag.has_attr("data-form"))
    if form_element:
        try:
            form_data = json.loads(str(form_element["data-form"]))
            if "xsrf_token" in form_data:
                return str(form_data["xsrf_token"])
        except (json.JSONDecodeError, KeyError):
            pass

    return None


def parse_user_points(html: str) -> int | None:
    """Points balance from the nav bar; None when the element is missing
    (session expired). Raises ValueError when the element text is malformed."""
    soup = BeautifulSoup(html, "html.parser")

    points_element = soup.find("span", class_="nav__points")
    if not points_element:
        return None

    points_text = points_element.text.strip()
    match = re.search(r"(\d+)", points_text)
    if not match:
        raise ValueError(f"Could not parse points: {points_text}")

    return int(match.group(1))


def parse_username(html: str) -> str | None:
    """Logged-in username from the nav area, or None when not present."""
    soup = BeautifulSoup(html, "html.parser")

    # Method 1: the user avatar link
    avatar_link = soup.find("a", class_="nav__avatar-inner-wrap")
    if avatar_link:
        href = str(avatar_link.get("href", "") or "")
        username_match = re.search(r"/user/([^/]+)", href)
        if username_match:
            return username_match.group(1)

    # Method 2: the user dropdown in the nav button container
    nav_container = soup.find("div", class_="nav__button-container")
    if nav_container:
        user_link = nav_container.find("a", href=re.compile(r"^/user/"))
        if user_link:
            href = str(user_link.get("href", "") or "")
            username_match = re.search(r"/user/([^/]+)", href)
            if username_match:
                return username_match.group(1)

    # Method 3: any /user/ link near the points element
    points_element = soup.find("span", class_="nav__points")
    if points_element:
        parent = points_element.parent
        while parent and parent.name != "nav":
            user_link = parent.find("a", href=re.compile(r"^/user/"))
            if user_link:
                href = str(user_link.get("href", "") or "")
                username_match = re.search(r"/user/([^/]+)", href)
                if username_match:
                    return username_match.group(1)
            parent = parent.parent

    return None


def parse_giveaway_list(
    html: str, mark_wishlist: bool = False, mark_dlc: bool = False
) -> list[dict[str, Any]]:
    """Parse a giveaway search/listing page into giveaway dicts.

    Skips pinned/"Featured" advertisement giveaways. Rows that fail to parse
    are logged and dropped rather than failing the whole page.
    ``mark_wishlist``/``mark_dlc`` tag every parsed row with the scan type
    it came from (wishlist page, DLC page).
    """
    soup = BeautifulSoup(html, "html.parser")

    giveaways = []
    giveaway_elements = soup.find_all("div", class_="giveaway__row-inner-wrap")

    for element in giveaway_elements:
        try:
            # Skip pinned/advertisement giveaways ("Featured" section at the
            # top of wishlist pages). The container class has changed over
            # time (pinned-giveaways__inner-wrap, then pinned-giveaways),
            # so match any pinned-giveaways* ancestor.
            if element.find_parent("div", class_=re.compile(r"^pinned-giveaways")):
                continue

            giveaway = parse_giveaway_element(element)
            if giveaway:
                giveaway["is_wishlist"] = mark_wishlist
                giveaway["is_dlc"] = mark_dlc
                giveaways.append(giveaway)
        except Exception as e:
            # Log error but continue parsing other giveaways
            logger.warning("giveaway_parse_failed", error=str(e))
            continue

    return giveaways


def parse_giveaway_element(element: Any) -> dict[str, Any] | None:
    """Parse one giveaway row element, or None if it has no usable link."""
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

    # Extract entries count. The links row is a div (not a span) containing
    # e.g. "1,234 entries 5 comments" — match digits with thousands commas.
    entries = 0
    entries_element = element.find("div", class_="giveaway__links")
    if entries_element:
        entries_text = entries_element.get_text(" ", strip=True)
        match = re.search(r"([\d,]+)\s+entr", entries_text)
        if match:
            entries = int(match.group(1).replace(",", ""))

    # Extract end time
    time_element = element.find("span", {"data-timestamp": True})
    end_time = None
    if time_element:
        timestamp = int(time_element["data-timestamp"])
        end_time = from_timestamp(timestamp)

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


def parse_giveaway_details(html: str) -> dict[str, Any]:
    """Parse a single giveaway page into a details dict (game_name only for now)."""
    soup = BeautifulSoup(html, "html.parser")

    heading = soup.find("a", class_="giveaway__heading__name")
    game_name = heading.text.strip() if heading else "Unknown"

    return {"game_name": game_name}


def parse_won_giveaways(html: str) -> list[dict[str, Any]]:
    """Parse the /giveaways/won page into won-giveaway dicts."""
    soup = BeautifulSoup(html, "html.parser")

    won_giveaways = []
    table_rows = soup.find_all("div", class_="table__row-inner-wrap")

    for row in table_rows:
        try:
            won = parse_won_giveaway_row(row)
            if won:
                won_giveaways.append(won)
        except Exception as e:
            logger.warning("won_giveaway_parse_failed", error=str(e))
            continue

    return won_giveaways


def parse_won_giveaway_row(row: Any) -> dict[str, Any] | None:
    """Parse one row of the /giveaways/won page, or None if unusable."""
    # Find the game name and giveaway link
    heading = row.find("a", class_="table__column__heading")
    if not heading:
        return None

    game_name = heading.text.strip()
    href = heading.get("href", "")

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
            won_at = from_timestamp(timestamp)
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


def parse_entered_giveaways(html: str) -> list[dict[str, Any]]:
    """Parse the /giveaways/entered page into entered-giveaway dicts."""
    soup = BeautifulSoup(html, "html.parser")

    entered_giveaways = []
    table_rows = soup.find_all("div", class_="table__row-inner-wrap")

    for row in table_rows:
        try:
            entered = parse_entered_giveaway_row(row)
            if entered:
                entered_giveaways.append(entered)
        except Exception as e:
            logger.warning("entered_giveaway_parse_failed", error=str(e))
            continue

    return entered_giveaways


def parse_entered_giveaway_row(row: Any) -> dict[str, Any] | None:
    """Parse one row of the /giveaways/entered page, or None if unusable."""
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
    fill_col = row.find("div", class_="table__column--width-fill")
    if fill_col:
        time_element = fill_col.find("span", {"data-timestamp": True})
        if time_element:
            try:
                timestamp = int(time_element["data-timestamp"])
                end_time = from_timestamp(timestamp)
            except (ValueError, KeyError):
                pass

    # Get entered_at timestamp (second timestamp in the row)
    entered_at = None
    if len(columns) >= 2:
        time_element = columns[1].find("span", {"data-timestamp": True})
        if time_element:
            try:
                timestamp = int(time_element["data-timestamp"])
                entered_at = from_timestamp(timestamp)
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


def parse_giveaway_game_id(html: str) -> int | None:
    """Steam game id from a giveaway page's featured wrapper, or None."""
    soup = BeautifulSoup(html, "html.parser")

    featured = soup.find("div", class_="featured__outer-wrap")
    if featured:
        game_id = featured.get("data-game-id")
        if game_id:
            return int(str(game_id))

    return None


def check_page_safety(html_content: str) -> dict[str, Any]:
    """
    Check if a giveaway page contains suspicious content.

    Analyzes the page text for forbidden words that might indicate
    a trap giveaway (e.g., "don't enter", "ban", "fake").

    Returns:
        Dictionary with safety check results:
            - is_safe: True if page appears safe
            - safety_score: Score from 0-100 (higher = safer)
            - bad_count: Number of bad words found
            - good_count: Number of good words found (false positives)
            - details: List of found bad words
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
