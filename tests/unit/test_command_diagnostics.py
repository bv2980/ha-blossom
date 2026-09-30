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
