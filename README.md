# SteamSelfGifter

[![Tests](https://github.com/kernelcoffee/SteamSelfGifter/actions/workflows/test.yml/badge.svg)](https://github.com/kernelcoffee/SteamSelfGifter/actions/workflows/test.yml)
[![Docker](https://github.com/kernelcoffee/SteamSelfGifter/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/kernelcoffee/SteamSelfGifter/actions/workflows/docker-publish.yml)
[![Python Version](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

SteamSelfGifter is an automated bot for entering Steam game giveaways on SteamGifts.com. It features a modern web interface for managing your giveaway entries, tracking wins, and configuring automation settings.

## Features

- **Web Dashboard**: Modern React-based UI for monitoring and control
- **Wishlist Integration**: Automatically enters giveaways for games on your Steam wishlist
- **DLC Support**: Optional support for DLC giveaways
- **Smart Auto-join**: Automatically enters giveaways based on customizable criteria:
  - Minimum price threshold
  - Minimum review score
  - Minimum number of reviews
- **Safety Detection**: Detects and avoids trap/scam giveaways with background safety checks
- **Win Tracking**: Track your wins and win rate statistics
- **Real-time Updates**: WebSocket-based live notifications
- **Analytics Dashboard**: View entry statistics and trends
- **Activity Logs**: View detailed logs of all bot activity

## Quick Start

### Docker (Recommended)

```bash
# Using the pre-built image from GitHub Container Registry
docker run -d \
  --name steamselfgifter \
  -p 8080:80 \
  -v steamselfgifter-data:/config \
  ghcr.io/kernelcoffee/steamselfgifter:latest

# Access the web interface at http://localhost:8080
```

Or with Docker Compose:

```bash
# Clone the repository
git clone https://github.com/kernelcoffee/SteamSelfGifter.git
cd SteamSelfGifter

# Start with Docker Compose
docker-compose up -d

# Access the web interface at http://localhost:8080
```

### Manual Installation

#### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -e .

# Start the backend
cd src
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

#### Frontend

```bash
cd frontend
npm install
npm run dev  # Development server at http://localhost:5173
```

## Configuration

1. Open the web interface
2. Go to **Settings**
3. Enter your SteamGifts PHPSESSID (see below)
4. Configure your preferences:
   - Enable/disable automation
   - Enable/disable DLC giveaways
   - Set auto-join criteria (min price, score, reviews)
   - Enable safety check for trap detection

### How to get your PHPSESSID

1. Sign in to [SteamGifts](https://www.steamgifts.com)
2. Open your browser's developer tools (F12)
3. Go to the **Application** tab (Chrome) or **Storage** tab (Firefox)
4. Find **Cookies** → `www.steamgifts.com`
5. Copy the `PHPSESSID` value
6. Paste it in the Settings page

## Architecture

```
SteamSelfGifter/
├── backend/              # FastAPI REST API + SQLite
│   ├── src/
│   │   ├── api/          # REST API endpoints
│   │   ├── core/         # Configuration, logging, exceptions
│   │   ├── db/           # Database session management
│   │   ├── models/       # SQLAlchemy ORM models
│   │   ├── repositories/ # Data access layer
│   │   ├── services/     # Business logic
│   │   ├── utils/        # SteamGifts/Steam API clients
│   │   └── workers/      # Background job scheduler
│   └── tests/            # Test suite (pytest)
├── frontend/             # React + TypeScript + Vite + TailwindCSS
│   └── src/
│       ├── components/   # Reusable UI components
│       ├── hooks/        # React Query hooks
│       ├── pages/        # Page components
│       └── services/     # API client
├── docs/                 # Documentation
├── Dockerfile            # Multi-stage single-container build
└── docker-compose.yml    # Docker deployment configuration
```

## API Documentation

Once the backend is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

When running via Docker, the API is available at:
- http://localhost:8080/api/v1/

## Development

### Running Tests

```bash
# Backend tests
cd backend
pip install -e ".[test]"
pytest

# Frontend build/lint
cd frontend
npm run lint
npm run build
```

### Database Migrations

The project uses Alembic for database migrations. Migrations run automatically on startup.

```bash
# Create a new migration after model changes
cd backend/src
alembic revision --autogenerate -m "description"

# Apply migrations manually
alembic upgrade head
```

## Contributing

We welcome contributions! Please see our [Contributing Guidelines](CONTRIBUTING.md) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This bot is for educational purposes only. Please ensure you comply with SteamGifts' terms of service and use this tool responsibly.