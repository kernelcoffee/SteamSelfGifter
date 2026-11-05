"""Time helpers.

The database stores naive UTC datetimes (SQLite has no timezone support), so
every "now" in the codebase must be naive UTC. ``datetime.utcnow()`` is
deprecated since Python 3.12; this helper is the single sanctioned replacement.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current UTC time as a naive datetime (to match stored values)."""
    return datetime.now(UTC).replace(tzinfo=None)


def from_timestamp(timestamp: int | float) -> datetime:
    """Unix timestamp -> naive UTC datetime (to match stored values).

    ``datetime.fromtimestamp()`` without a tz yields naive *local* time,
    which silently skews comparisons against ``utcnow()`` on non-UTC hosts.
    """
    return datetime.fromtimestamp(timestamp, UTC).replace(tzinfo=None)


def to_naive_utc(dt: datetime) -> datetime:
    """Aware datetime -> naive UTC (to match stored values).

    For values that carry their own zone, such as APScheduler's
    ``next_run_time``. Dropping the offset with ``replace(tzinfo=None)``
    instead keeps the wall-clock time of whatever zone the value was in.

    Raises:
        ValueError: ``dt`` is naive; ``astimezone()`` would read it as the
            host's local time, so it is refused rather than guessed.
    """
    if dt.tzinfo is None:
        raise ValueError("to_naive_utc() needs an aware datetime; naive values are already UTC")
    return dt.astimezone(UTC).replace(tzinfo=None)


def isoformat_z(dt: datetime) -> str:
    """Datetime -> UTC ISO 8601 with a 'Z' suffix, as API responses carry.

    A naive value is taken as UTC (the stored convention); an aware one is
    converted to UTC first.
    """
    if dt.tzinfo is not None:
        dt = to_naive_utc(dt)
    return dt.isoformat() + "Z"
