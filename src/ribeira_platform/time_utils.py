from __future__ import annotations

from datetime import datetime, timezone


def parse_aware(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and reject naive datetimes."""
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")
    return parsed


def canonical_utc(value: str) -> str:
    return parse_aware(value).astimezone(timezone.utc).isoformat()
