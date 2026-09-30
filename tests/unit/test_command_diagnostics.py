"""Exercise HTTP evidence with synthetic secrets and realistic response envelopes."""

import json
import time

import pytest
from blossom_test_client import api
from blossom_test_client.command_diagnostics import response_summary
from test_api import Response, Session

SCOPE = {
    "member_id": "private-member",
    "company_id": "private-company",
    "installation_id": "private-installation",
}


def client(responses):
    return api.BlossomClient(
        Session(responses), api.Tokens("secret-refresh", "secret-access", time.monotonic() + 300)
    )


async def test_success_http_can_contain_application_rejection_without_replay():
    instance = client(
        [
            Response(
                200,
                {
                    "data": {"accepted": False, "status": "Rejected"},
                    "message": "private email and token",
                },
            )
        ]
    )
    assert await instance.start_home_session(SCOPE, "private-card") == {}
    trace = instance.last_command_http
    assert trace["outcome"] == "http_success"
    assert trace["attempts"][0]["response"]["results"] == {
        "data.accepted": False,
        "data.status": "rejected",
    }
    assert trace["duration_ms"] >= 0
    assert len(instance.session.calls) == 1
    assert "private" not in json.dumps(trace)
    assert "secret" not in json.dumps(trace)


@pytest.mark.parametrize(
    "status,exception",
    [(403, api.PermissionError), (429, api.RateLimitError), (500, api.ConnectionError)],
)
async def test_error_response_evidence_is_retained(status, exception):
    instance = client([Response(status, {"error": {"code": "Rejected", "message": "SECRET"}})])
    with pytest.raises(exception):
        await instance.start_home_session(SCOPE, "private-card")
    assert instance.last_command_http["attempts"][0]["http_status"] == status
    assert instance.last_command_http["outcome"] == exception.__name__
    assert "SECRET" not in json.dumps(instance.last_command_http)


async def test_transport_failure_does_not_keep_previous_http_evidence():
    instance = client([Response(204), Response(error=TimeoutError("SECRET"))])
    await instance.stop_home_session(SCOPE)
    assert instance.last_command_http["attempts"][0]["response"] == {"body": "empty"}
    with pytest.raises(api.ConnectionError):
        await instance.stop_home_session(SCOPE)
    assert instance.last_command_http["attempts"] == []
    assert "SECRET" not in json.dumps(instance.last_command_http)


async def test_401_evidence_includes_both_attempts_without_token_response():
    instance = client(
        [
            Response(401),
            Response(
                200,
                {"access_token": "NEWSECRET", "refresh_token": "REFRESHSECRET", "expires_in": 3600},
            ),
            Response(202),
        ]
    )
    await instance.start_home_session(SCOPE, "private-card")
    assert [row["http_status"] for row in instance.last_command_http["attempts"]] == [401, 202]
    assert "SECRET" not in json.dumps(instance.last_command_http)


async def test_body_read_failure_after_success_does_not_replay():
    response = Response(202)

    async def fail(size=None):
        raise TimeoutError("SECRET")

    response.read = fail
    instance = client([response])
    await instance.stop_home_session(SCOPE)
    assert instance.last_command_http["attempts"][0]["response"] == {"body": "read_failed"}
    assert len(instance.session.calls) == 1


def test_response_privacy_and_bounds():
    result = response_summary(
        json.dumps(
            {
                "status": "SECRET",
                "error": {"code": "user@example.invalid", "message": "SECRET"},
                "token": "SECRET",
                "cardId": "SECRET",
                "success": False,
            }
        ).encode()
    )
    assert result["results"] == {
        "status": "unrecognized",
        "error.code": "unrecognized",
        "success": False,
    }
    assert "SECRET" not in json.dumps(result)
    assert response_summary(b"SECRET") == {"body": "non_json"}
    assert response_summary(b"x" * 16385) == {"body": "too_large"}


@pytest.mark.parametrize("value", [0, 1, -1, 201, 403, "0", "201"])
def test_small_numeric_status_is_visible_without_guessing_its_meaning(value):
    result = response_summary(json.dumps({"status": value}).encode())
    assert result["results"]["status"] == int(value)
    assert result["value_details"]["status"]["type"] == (
        "string" if isinstance(value, str) else "integer"
    )


@pytest.mark.parametrize(
    "value",
    [
        987654321,
        "987654321",
        "--1",
        "１２",
        1.5,
        "user@example.invalid",
        "Bearer SECRET",
        "NEW_UNKNOWN_ENUM",
    ],
)
def test_unknown_status_keeps_only_type_and_shape(value):
    result = response_summary(json.dumps({"status": value}).encode())
    assert result["results"]["status"] == "unrecognized"
    assert str(value) not in json.dumps(result)


def test_structured_status_preserves_known_fields_but_not_personal_keys():
    result = response_summary(
        json.dumps(
            {
                "status": {
                    "code": 403,
                    "result": [{"status": "NotAuthorized", "message": "SECRET"}],
                    "customer@example.invalid": "SECRET",
                    "token": "SECRET",
                }
            }
        ).encode()
    )
    assert result["results"] == {"status.code": 403, "status.result[0].status": "notauthorized"}
    assert result["value_details"]["status"]["type"] == "object"
    assert result["value_details"]["status"]["omitted_field_count"] == 2
    assert "SECRET" not in json.dumps(result)
    assert "customer@" not in json.dumps(result)


def test_result_traversal_is_bounded_and_handles_root_scalars():
    result = response_summary(json.dumps({"status": ["Accepted"] * 100}).encode())
    assert len(result["results"]) == 3
    assert result["value_details"]["status"]["truncated"] is True
    value = {"status": 1}
    for _ in range(6):
        value = {"data": value}
    result = response_summary(json.dumps(value).encode())
    assert result["value_details"]["data.data.data.data"]["truncated"] is True
    assert response_summary(b'"Rejected"')["results"] == {"response": "rejected"}
    assert response_summary(b"false")["results"] == {"response": False}


async def test_actual_201_numeric_status_is_recorded_without_resending():
    instance = client([Response(201, {"status": 1})])
    await instance.start_home_session(SCOPE, "private-card")
    response = instance.last_command_http["attempts"][0]["response"]
    assert response["results"] == {"status": 1}
    assert response["value_details"]["status"]["type"] == "integer"
    assert len(instance.session.calls) == 1
