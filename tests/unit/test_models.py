"""Guard units, missing data and private-field exclusion."""

import json
from pathlib import Path

import pytest
from blossom_test_client.api import ProtocolError
from blossom_test_client.models import (
    active_session_summary,
    member_name,
    number,
    scope_choices,
    session_amount,
    session_summaries,
    timestamp,
)


def test_session_units_sorting_and_whitelist():
    rows = [
        {
            "start": "2026-09-20T12:00:00Z",
            "end": "2026-09-20T13:00:00Z",
            "kwh": 12.5,
            "duration": 60,
            "status": "COMPLETED",
            "type": "Home",
            "hcpPrice": 4.25,
            "mspPrice": 5,
            "vat": 21,
            "user": {"email": "private"},
        },
        {"start": "2026-09-21T13:00:00+02:00", "end": None, "kwh": 0, "status": "IN_PROGRESS"},
    ]
    result = session_summaries(rows)
    assert result[0]["energy_kwh"] == 0
    assert result[1]["duration_minutes"] == 60
    assert result[1]["energy_kwh"] == 12.5
    assert result[1]["amount_eur"] == 4.25
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


def test_public_amount_includes_vat_like_the_blossom_web_app():
    assert session_amount("Public", None, 10, 6) == 10.6
    assert session_amount("Public", None, 10, None) == 12.1
    assert session_amount("Home", 7.5, 10, 21) == 7.5


def test_active_session_uses_active_endpoint_field_names():
    result = active_session_summary(
        [{"time_started_session": "2026-09-25T12:00:00Z", "kWh": 3.2, "remuneration_type": "hcp"}]
    )
    assert result == {
        "start": "2026-09-25T12:00:00+00:00",
        "last_update": None,
        "energy_kwh": 3.2,
        "remuneration_type": "hcp",
        "device_status": None,
        "session_status": None,
        "vehicle_current": None,
        "vehicle_phases": None,
    }


def test_active_session_uses_observed_nested_session_shape():
    result = active_session_summary(
        [
            {
                "deviceStatus": "charging",
                "kind": "home",
                "session": {
                    "time_started_session": "2026-09-26T09:30:00Z",
                    "time_last_update": "2026-09-26T09:31:00Z",
                    "kWh": "4.75",
                    "remuneration_type": "hcp",
                    "status": "ACTIVE",
                    "vehicle_current": 13,
                    "vehicle_phases": 3,
                    "private": {"email": "must-not-appear"},
                },
            }
        ]
    )
    assert result == {
        "start": "2026-09-26T09:30:00+00:00",
        "last_update": "2026-09-26T09:31:00+00:00",
        "energy_kwh": 4.75,
        "remuneration_type": "hcp",
        "device_status": "charging",
        "session_status": "ACTIVE",
        "vehicle_current": 13.0,
        "vehicle_phases": 3.0,
    }
    assert "must-not-appear" not in str(result)


def test_member_name_prefers_readable_company_data_without_an_id():
    assert member_name({"company": {"name": "Example Energy"}, "id": "private"}) == (
        "Example Energy"
    )
    assert member_name({"email": "person@example.invalid"}) == "person@example.invalid"
    assert member_name({"id": "private"}) == "Blossom account"


def test_manifest_and_code_versions_match():
    from blossom_test_client.const import INTEGRATION_VERSION

    manifest = json.loads(
        (Path(__file__).parents[2] / "custom_components/blossom_energy/manifest.json").read_text()
    )
    assert manifest["version"] == INTEGRATION_VERSION
