# Test Scripts

Utility scripts for fetching SteamGifts pages to help debug HTML parsing.

## Prerequisites

These scripts read the PHPSESSID from the database. Make sure you have:
1. Configured your PHPSESSID in the app settings
2. The database exists at `backend/data/steamselfgifter.db`

## Usage

Run from the `backend` directory:

```bash
cd backend
source .venv/bin/activate

# Fetch wishlist page
python tests/scripts/fetch_wishlist_page.py

# Fetch won giveaways page
python tests/scripts/fetch_won_page.py
```

## Output

HTML files are saved to `tests/scripts/output/` (gitignored).
