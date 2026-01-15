# SteamSelfGifter Backend

FastAPI-based REST API for SteamSelfGifter with SQLite persistence, WebSocket support, and automated giveaway entry.

## Tech Stack

- **Framework**: FastAPI
- **Database**: SQLite with SQLAlchemy (async)
- **Python**: 3.13+

## Directory Structure

```
backend/
├── src/
│   ├── api/                    # FastAPI routes and schemas
│   │   ├── routers/           # API endpoint routers
│   │   └── schemas/           # Pydantic models
│   ├── core/                   # Config, logging, exceptions
│   ├── db/                     # Database session
│   ├── models/                 # SQLAlchemy ORM models
│   ├── repositories/           # Data access layer
│   ├── services/               # Business logic layer
│   ├── utils/                  # Steam/SteamGifts clients
│   └── workers/                # Background scheduler
├── tests/                      # Test suite
├── data/                       # SQLite database (dev)
└── pyproject.toml              # Dependencies
```

## Development

### Setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### Running

```bash
cd src
uvicorn api.main:app --reload --port 8000
```

API available at:
- REST API: http://localhost:8000
- Swagger UI: http://localhost:8000/docs
- WebSocket: ws://localhost:8000/ws/events

### Testing

```bash
pytest                    # Run all tests
pytest --cov=src          # With coverage
pytest -v -s              # Verbose output
```

### Database Migrations

Migrations use Alembic and run automatically on startup.

```bash
cd src

# Create a new migration after model changes
alembic revision --autogenerate -m "description"

# Apply migrations manually
alembic upgrade head

# View migration history
alembic history
```

## Architecture

### Layers

1. **API Layer** (`api/`) - HTTP endpoints, request/response schemas
2. **Service Layer** (`services/`) - Business logic, orchestration
3. **Repository Layer** (`repositories/`) - Database operations
4. **Model Layer** (`models/`) - SQLAlchemy ORM models

### Key Services

- **GiveawayService** - Giveaway scanning, entering, tracking
- **GameService** - Steam game data caching
- **SchedulerService** - Background automation
- **NotificationService** - Activity logging

### Background Workers (`workers/`)

- **automation.py** - Main automation cycle (scan, enter, sync wins)
- **safety_checker.py** - Background safety checks for trap detection
- **scheduler.py** - APScheduler manager for background jobs

### External Clients

- **SteamGiftsClient** (`utils/steamgifts_client.py`) - Web scraping
- **SteamClient** (`utils/steam_client.py`) - Steam API integration
