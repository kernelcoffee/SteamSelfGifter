"""POST /giveaways/{code}/enter, then fire the win_check job it scheduled.

The job registered by the enter request must keep working after the request
finished and its dependencies closed their HTTP clients.
"""

from collections.abc import Callable
from datetime import timedelta
from functools import partial
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from core.time import utcnow
from models.giveaway import Giveaway
from services.scheduler_service import WIN_CHECK_JOB_ID
from services.settings_service import SettingsService
from tests.integration_mocked.conftest import RoutedTransport
from utils.steam_client import SteamClient
from utils.steamgifts_client import SteamGiftsClient
from workers.scheduler import SchedulerManager
from workers.win_check import run_win_check

FIXTURES = Path(__file__).parent.parent / "fixtures"

pytestmark = pytest.mark.usefixtures("uncached_win_check_logger")


@pytest.mark.asyncio
async def test_enter_endpoint_schedules_win_check_that_runs_after_response(
    test_client: AsyncClient, async_engine: AsyncEngine
) -> None:
    """The enter endpoint registers the module-level run_win_check at
    end_time+5min; fired after the response, it starts a fresh SteamGifts
    client and syncs the won page without error."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)
    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="ENTR1", url="/giveaway/ENTR1/", game_name="Game", price=10, end_time=end_time))
        await session.commit()

    homepage = (FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")
    won_page = (FIXTURES / "empty_search_page.html").read_text(encoding="utf-8")
    request_transport = RoutedTransport()
    request_transport.add("GET", "/", httpx.Response(200, text=homepage))
    request_transport.add("POST", "/ajax.php", httpx.Response(200, json={"type": "success"}))
    job_transport = RoutedTransport()
    job_transport.add("GET", "/", httpx.Response(200, text=homepage))
    job_transport.add("GET", "/giveaways/won", httpx.Response(200, text=won_page))
    steam_transport = RoutedTransport()

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("api.dependencies.SteamGiftsClient", partial(SteamGiftsClient, transport=request_transport)),
            patch("api.dependencies.SteamClient", partial(SteamClient, transport=steam_transport)),
        ):
            response = await test_client.post("/api/v1/giveaways/ENTR1/enter", json={"entry_type": "manual"})
        assert response.status_code == 200, response.text

        job = manager.get_job(WIN_CHECK_JOB_ID)
        assert job is not None
        assert job.func is run_win_check
        assert job.next_run_time.replace(tzinfo=None) == end_time + timedelta(minutes=5)

        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", partial(SteamGiftsClient, transport=job_transport)),
            patch("workers.context.SteamClient", partial(SteamClient, transport=steam_transport)),
            capture_logs() as logs,
        ):
            await job.func(*job.args, **job.kwargs)
    finally:
        manager.stop(wait=False)

    assert not any(entry["log_level"] == "error" for entry in logs), logs
    assert [(r.method, r.url.path) for r in job_transport.requests] == [("GET", "/"), ("GET", "/giveaways/won")]


@pytest.mark.asyncio
async def test_enter_endpoint_closes_request_clients_and_job_does_not_reuse_them(
    test_client: AsyncClient, async_engine: AsyncEngine
) -> None:
    """The enter request's SteamGifts and Steam clients are closed once the
    response is sent, and the win_check job it registered starts clients of
    its own instead of touching those closed ones."""
    session_maker = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    end_time = utcnow() + timedelta(days=1)
    async with session_maker() as session:
        await SettingsService(session).update_settings(phpsessid="test_session")
        session.add(Giveaway(code="ENTR2", url="/giveaway/ENTR2/", game_name="Game", price=10, end_time=end_time))
        await session.commit()

    homepage = (FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")
    won_page = (FIXTURES / "empty_search_page.html").read_text(encoding="utf-8")
    request_transport = RoutedTransport()
    request_transport.add("GET", "/", httpx.Response(200, text=homepage))
    request_transport.add("POST", "/ajax.php", httpx.Response(200, json={"type": "success"}))
    job_transport = RoutedTransport()
    job_transport.add("GET", "/", httpx.Response(200, text=homepage))
    job_transport.add("GET", "/giveaways/won", httpx.Response(200, text=won_page))
    steam_transport = RoutedTransport()

    request_clients: list[SteamGiftsClient | SteamClient] = []
    job_clients: list[SteamGiftsClient | SteamClient] = []

    def recording(
        cls: type[SteamGiftsClient] | type[SteamClient],
        transport: RoutedTransport,
        sink: list[SteamGiftsClient | SteamClient],
    ) -> Callable[..., SteamGiftsClient | SteamClient]:
        """Client factory on ``transport`` that records every client it builds."""

        def build(*args: Any, **kwargs: Any) -> SteamGiftsClient | SteamClient:
            client = cls(*args, **kwargs, transport=transport)
            sink.append(client)
            return client

        return build

    manager = SchedulerManager()
    manager.start()
    try:
        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("api.dependencies.SteamGiftsClient", recording(SteamGiftsClient, request_transport, request_clients)),
            patch("api.dependencies.SteamClient", recording(SteamClient, steam_transport, request_clients)),
        ):
            response = await test_client.post("/api/v1/giveaways/ENTR2/enter", json={"entry_type": "manual"})
        assert response.status_code == 200, response.text
        assert response.json()["success"] is True

        # Both request-scoped clients were built and are closed after the response.
        assert sorted(type(c).__name__ for c in request_clients) == ["SteamClient", "SteamGiftsClient"]
        assert all(client._client is None for client in request_clients)
        request_traffic = len(request_transport.requests)

        job = manager.get_job(WIN_CHECK_JOB_ID)
        assert job is not None
        assert job.args == () and job.kwargs == {}

        with (
            patch("services.scheduler_service.scheduler_manager", manager),
            patch("workers.context.AsyncSessionLocal", session_maker),
            patch("workers.context.SteamGiftsClient", recording(SteamGiftsClient, job_transport, job_clients)),
            patch("workers.context.SteamClient", recording(SteamClient, steam_transport, job_clients)),
            capture_logs() as logs,
        ):
            await job.func(*job.args, **job.kwargs)

        rescheduled = manager.get_job(WIN_CHECK_JOB_ID)
    finally:
        manager.stop(wait=False)

    assert not any(entry["log_level"] == "error" for entry in logs), logs
    assert len(request_transport.requests) == request_traffic
    assert [(r.method, r.url.path) for r in job_transport.requests] == [("GET", "/"), ("GET", "/giveaways/won")]
    assert len(job_clients) == 2
    assert not set(map(id, job_clients)) & set(map(id, request_clients))
    assert all(client._client is None for client in job_clients)
    assert rescheduled is not None
    assert rescheduled.next_run_time.replace(tzinfo=None) == end_time + timedelta(minutes=5)
