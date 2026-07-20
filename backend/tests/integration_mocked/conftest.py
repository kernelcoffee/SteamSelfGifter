"""Shared fixtures for mocked-HTTP integration tests."""

from pathlib import Path

import httpx
import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"


class RoutedTransport(httpx.MockTransport):
    """MockTransport with a per-path response table and request recording.

    Register responses with add(); each registered path serves its responses
    in order, repeating the last one once exhausted. Every request the client
    makes is recorded in self.requests for assertions.
    """

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], list[httpx.Response]] = {}
        self.requests: list[httpx.Request] = []
        super().__init__(self._handle)

    def add(self, method: str, path: str, *responses: httpx.Response) -> None:
        self._routes[(method.upper(), path)] = list(responses)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        key = (request.method, request.url.path)
        responses = self._routes.get(key)
        if not responses:
            raise AssertionError(f"Unexpected request: {request.method} {request.url}")
        if len(responses) > 1:
            return responses.pop(0)
        return responses[0]


@pytest.fixture
def transport() -> RoutedTransport:
    return RoutedTransport()


@pytest.fixture(scope="session")
def wishlist_html() -> str:
    return (FIXTURES / "wishlist_page.html").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def empty_search_html() -> str:
    return (FIXTURES / "empty_search_page.html").read_text(encoding="utf-8")


@pytest.fixture
def no_sleep(mocker):
    """Make retry backoffs instant; returns the mock for delay assertions."""
    return mocker.patch("asyncio.sleep")
