#!/usr/bin/env python3
"""
Script to fetch and save the /giveaways/won page HTML for analysis.

Run this from the backend directory:
    cd backend
    source .venv/bin/activate
    python tests/scripts/fetch_won_page.py

The HTML will be saved to tests/scripts/output/won_page.html
"""

import asyncio
import os
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from utils.steamgifts_client import SteamGiftsClient
from sqlalchemy import create_engine, text


def get_session_from_db():
    """Read PHPSESSID and user_agent from the database."""
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'steamselfgifter.db')
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT phpsessid, user_agent FROM settings LIMIT 1"))
        row = result.fetchone()
        if row:
            return row[0], row[1]
    return None, None


async def main():
    phpsessid, user_agent = get_session_from_db()

    if not phpsessid:
        print("Error: PHPSESSID not configured in database settings")
        return

    print("Fetching /giveaways/won page...")

    client = SteamGiftsClient(
        phpsessid=phpsessid,
        user_agent=user_agent or "Mozilla/5.0",
    )

    await client.start()

    try:
        # Get the raw HTML
        response = await client._client.get("https://www.steamgifts.com/giveaways/won")

        if response.status_code != 200:
            print(f"Error: Got status code {response.status_code}")
            return

        # Save HTML to file
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "won_page.html")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)

        print(f"Saved HTML to {output_path}")
        print(f"File size: {len(response.text)} bytes")

        # Also try to parse it
        wins = await client.get_won_giveaways()
        print(f"\nParsed {len(wins)} won giveaways:")
        for win in wins[:5]:  # Show first 5
            print(f"  - {win['game_name']} (code: {win['code']}, game_id: {win['game_id']})")

        if len(wins) > 5:
            print(f"  ... and {len(wins) - 5} more")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
