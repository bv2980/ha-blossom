"""Retention boundaries must not depend on new commands or mutable caller data."""

from datetime import UTC, datetime, timedelta

from blossom_test_client.command_history import retained_history


def test_history_keeps_latest_twenty_independent_records():
    now = datetime(2026, 9, 30, tzinfo=UTC)
    rows = [
        {
            "action": "start",
            "attempt_id": str(i),
            "requested_at": (now - timedelta(minutes=i)).isoformat(),
            "polls": [],
        }
        for i in range(30)
    ]
    history = retained_history(rows, now)
    assert len(history) == 20
    assert [row["attempt_id"] for row in history] == [str(i) for i in reversed(range(20))]
    rows[0]["polls"].append({"private": "must-not-leak"})
    assert history[-1]["polls"] == []


def test_history_expires_at_seven_days_and_rejects_bad_timestamps():
    now = datetime(2026, 9, 30, tzinfo=UTC)
    rows = [
        {"action": "stop", "requested_at": value}
        for value in (
            (now - timedelta(days=7)).isoformat(),
            (now - timedelta(days=7) + timedelta(seconds=1)).isoformat(),
            (now + timedelta(seconds=1)).isoformat(),
            "2026-09-29T00:00:00",
            "broken",
            None,
            {},
        )
    ]
    rows.extend([None, {}, {"action": "other", "requested_at": now.isoformat()}])
    assert len(retained_history(rows, now)) == 1
    assert retained_history(rows, now)[0] == rows[1]
    assert retained_history(None, now) == []
