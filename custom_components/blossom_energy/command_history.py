"""Bounded, local command history with deterministic retention."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

HISTORY_LIMIT = 20
HISTORY_AGE = timedelta(days=7)


def requested_time(attempt):
    try:
        value = datetime.fromisoformat(attempt["requested_at"])
        return value.astimezone(UTC) if value.tzinfo is not None else None
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def retained_history(attempts, now):
    """Drop invalid, expired and future entries; return independent oldest-first copies."""
    if not isinstance(attempts, list):
        return []
    valid = []
    for attempt in attempts:
        if not isinstance(attempt, dict) or attempt.get("action") not in ("start", "stop"):
            continue
        requested = requested_time(attempt)
        if requested is not None and now - HISTORY_AGE < requested <= now:
            valid.append((requested, attempt))
    valid.sort(key=lambda row: row[0])
    return [deepcopy(attempt) for _, attempt in valid[-HISTORY_LIMIT:]]
