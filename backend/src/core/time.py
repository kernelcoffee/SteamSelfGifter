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
