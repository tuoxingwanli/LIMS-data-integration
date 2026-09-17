"""Time helpers used by persisted integration records."""

from datetime import datetime, timezone


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for API and database records."""

    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
