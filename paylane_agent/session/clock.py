"""Fixed UTC clock so age checks are deterministic."""
from datetime import datetime, timedelta, timezone

# Fixed "now" for tests and demo runs.
DEFAULT_NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)
REFUND_WINDOW = timedelta(days=30)


def parse_utc(value: str) -> datetime:
    """Parse an ISO-8601 timestamp; naive values are treated as UTC."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class Clock:
    def __init__(self, now: datetime = DEFAULT_NOW):
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        self._now = now.astimezone(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def age(self, timestamp: str) -> timedelta:
        return self._now - parse_utc(timestamp)

    def within_refund_window(self, timestamp: str) -> bool:
        """True only if strictly less than 30 elapsed days. Exactly 30 escalates."""
        age = self.age(timestamp)
        return timedelta(0) <= age < REFUND_WINDOW
