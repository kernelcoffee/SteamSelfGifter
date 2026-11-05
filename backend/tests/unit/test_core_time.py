"""Unit tests for the UTC helpers in core.time."""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from core.time import isoformat_z, to_naive_utc


@pytest.mark.parametrize(
    ("aware", "expected"),
    [
        (datetime(2030, 1, 15, 12, 0, tzinfo=UTC), datetime(2030, 1, 15, 12, 0)),
        (datetime(2030, 1, 15, 7, 0, tzinfo=ZoneInfo("America/New_York")), datetime(2030, 1, 15, 12, 0)),
        (datetime(2030, 1, 15, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo")), datetime(2030, 1, 15, 12, 0)),
        (datetime(2030, 1, 1, 0, 30, tzinfo=timezone(timedelta(hours=1))), datetime(2029, 12, 31, 23, 30)),
    ],
)
def test_to_naive_utc_converts_to_utc_before_dropping_the_zone(aware: datetime, expected: datetime) -> None:
    """The wall-clock time is converted to UTC, not kept from the source zone."""
    result = to_naive_utc(aware)

    assert result == expected
    assert result.tzinfo is None


def test_to_naive_utc_rejects_naive_input() -> None:
    """A naive value is refused instead of being read as the host's local time."""
    with pytest.raises(ValueError, match="aware datetime"):
        to_naive_utc(datetime(2030, 1, 15, 12, 0))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (datetime(2030, 1, 15, 21, 0, tzinfo=ZoneInfo("Asia/Tokyo")), "2030-01-15T12:00:00Z"),
        (datetime(2030, 7, 1, 8, 30, 15, tzinfo=UTC), "2030-07-01T08:30:15Z"),
        (datetime(2030, 1, 15, 12, 0), "2030-01-15T12:00:00Z"),
    ],
)
def test_isoformat_z_serialises_utc_with_z(non_utc_host: None, value: datetime, expected: str) -> None:
    """Aware values are converted to UTC; naive ones are taken as stored UTC,
    whatever the host's local zone."""
    assert isoformat_z(value) == expected
