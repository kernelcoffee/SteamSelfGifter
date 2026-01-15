"""Pytest fixtures for integration tests.

These tests run against real SteamGifts with actual credentials.
Set STEAMGIFTS_PHPSESSID environment variable or use --phpsessid option.
"""

import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from models.base import Base


def pytest_addoption(parser):
    """Add command line options for integration tests."""
    parser.addoption(
        "--phpsessid",
        action="store",
        default=None,
        help="SteamGifts PHPSESSID cookie for integration tests",
    )
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests against real SteamGifts",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires --run-integration)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --run-integration is passed."""
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(reason="need --run-integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@pytest.fixture
def phpsessid(request):
    """Get PHPSESSID from command line or environment."""
    # Command line takes precedence
    cli_phpsessid = request.config.getoption("--phpsessid")
    if cli_phpsessid:
        return cli_phpsessid

    # Fall back to environment variable
    env_phpsessid = os.environ.get("STEAMGIFTS_PHPSESSID")
    if env_phpsessid:
        return env_phpsessid

    pytest.skip("No PHPSESSID provided (use --phpsessid or STEAMGIFTS_PHPSESSID env var)")


@pytest.fixture
def user_agent():
    """Default user agent for tests."""
    return "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0"


@pytest_asyncio.fixture
async def integration_db():
    """Create an in-memory database for integration tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session

    await engine.dispose()
