#!/usr/bin/env python3
"""
Fetch a single giveaway page HTML for parser analysis / fixture refresh.

Run this from the backend directory:
    cd backend
    source .venv/bin/activate
    python tests/scripts/fetch_giveaway_page.py <giveaway_code>

The HTML will be saved to tests/scripts/output/giveaway_page.html.
Scrub usernames, avatar URLs and xsrf tokens before committing as a fixture
(see tests/fixtures/giveaway_page.html).
"""

import asyncio
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from sqlalchemy import create_engine, text

from utils.steamgifts_client import SteamGiftsClient


def get_session_from_db():
    """Read PHPSESSID and user_agent from the database."""
    db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "steamselfgifter.db")
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT phpsessid, user_agent FROM settings LIMIT 1"))
        row = result.fetchone()
        if row:
            return row[0], row[1]
    return None, None


async def main():
    if len(sys.argv) != 2:
        print("Usage: python tests/scripts/fetch_giveaway_page.py <giveaway_code>")
        sys.exit(1)
    code = sys.argv[1]

    phpsessid, user_agent = get_session_from_db()
    if not phpsessid:
        print("No PHPSESSID found in the database — configure it in the app settings first.")
        sys.exit(1)

    client = SteamGiftsClient(phpsessid=phpsessid, user_agent=user_agent)
    await client.start()
    try:
        response = await client._get(f"{client.BASE_URL}/giveaway/{code}/")
        out_dir = os.path.join(os.path.dirname(__file__), "output")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, "giveaway_page.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"Saved {len(response.text)} bytes to {out_path}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
