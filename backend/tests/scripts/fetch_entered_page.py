#!/usr/bin/env python3
"""
Script to fetch and save the /giveaways/entered page HTML for analysis.

Run this from the backend directory:
    cd backend
    source .venv/bin/activate
    python tests/scripts/fetch_entered_page.py

The HTML will be saved to tests/scripts/output/entered_page.html
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
    # Try config directory first (Docker/production), then data directory (local dev)
    config_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'config', 'steamselfgifter.db')
    data_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'steamselfgifter.db')
    db_path = config_path if os.path.exists(config_path) else data_path
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

    print("Fetching /giveaways/entered page...")

    client = SteamGiftsClient(
        phpsessid=phpsessid,
        user_agent=user_agent or "Mozilla/5.0",
    )

    await client.start()

    try:
        # Get the raw HTML
        response = await client._client.get("https://www.steamgifts.com/giveaways/entered")

        if response.status_code != 200:
            print(f"Error: Got status code {response.status_code}")
            return

        # Save HTML to file
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        output_path = os.path.join(output_dir, "entered_page.html")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(response.text)

        print(f"Saved HTML to {output_path}")
        print(f"File size: {len(response.text)} bytes")

        # Use the client's parsing method
        entered = await client.get_entered_giveaways()
        print(f"\nFound {len(entered)} entered giveaways")

        for i, ga in enumerate(entered[:10]):  # Show first 10
            print(f"  {i+1}. {ga['game_name']} (code: {ga['code']}, price: {ga['price']}P, game_id: {ga['game_id']})")

        if len(entered) > 10:
            print(f"  ... and {len(entered) - 10} more")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())