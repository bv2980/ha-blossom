"""Guard units, missing data and private-field exclusion."""

import pytest
from blossom_test_client.api import ProtocolError
from blossom_test_client.models import number, scope_choices, session_summaries, timestamp


def test_session_units_sorting_and_whitelist():
    rows = [
        {
            "start": "2026-09-20T12:00:00Z",
            "end": "2026-09-20T13:00:00Z",
            "kwh": 12.5,
            "duration": 60,
            "status": "COMPLETED",
            "user": {"email": "private"},
        },
        {"start": "2026-09-21T13:00:00+02:00", "end": None, "kwh": 0, "status": "IN_PROGRESS"},
    ]
    result = session_summaries(rows)
    assert result[0]["energy_kwh"] == 0
    assert result[1]["duration_minutes"] == 60
    assert result[1]["energy_kwh"] == 12.5
    assert "private" not in str(result)
    assert "2026-09-21T11:00:00+00:00" == result[0]["start"]


def test_empty_is_valid_but_unknown_dates_are_not():
    assert session_summaries([]) == []
    with pytest.raises(ProtocolError):
        session_summaries([{"unexpected": "data"}])
    assert timestamp("2026-09-20T12:00:00") is None


@pytest.mark.parametrize("value", [None, True, -1, "NaN", "Infinity", "unknown"])
def test_invalid_measurements_are_unknown(value):
    assert number(value) is None


def test_explicit_scope_selection_has_all_candidates():
    user = {
        "members": [{"id": "a", "companyId": "ca"}, {"id": "b", "companyId": "cb"}],
        "installations": [{"id": "i"}, {"id": "j"}],
    }
    members, installations = scope_choices(user)
    assert set(members) == {"a", "b"}
    assert set(installations) == {"i", "j"}


def test_session_list_is_bounded():
    row = {"start": "2026-09-20T12:00:00Z"}
    assert len(session_summaries([row] * 30)) == 20
