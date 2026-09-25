"""Synthetic HTTP tests: never connect to a real Blossom account."""

import asyncio
import base64
import hashlib
import time
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
from blossom_test_client import api


class Response:
    def __init__(self, status=200, data=None, headers=None, error=None):
        self.status, self.data, self.headers, self.error = status, data, headers or {}, error

    async def __aenter__(self):
        await asyncio.sleep(0)
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return self.data

    async def read(self):
        return b"login form"


class Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        result = self.responses.pop(0)
        return result(method, url, kwargs) if callable(result) else result

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


def token_response(refresh="new-refresh", access="new-access"):
    return Response(data={"refresh_token": refresh, "access_token": access, "expires_in": 3600})


def test_pkce_and_callback_validation():
    verifier, challenge = api.pkce_pair()
    assert len(verifier) >= 43
    assert challenge == base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert api.callback_code(api.APP_ORIGIN + "?state=expected&code=code", "expected") == "code"
    for url in (
        "https://evil.example/?state=expected&code=code",
        api.APP_ORIGIN + "?state=wrong&code=code",
        api.APP_ORIGIN + "?state=expected&code=a&code=b",
        api.APP_ORIGIN + "/other?state=expected&code=code",
    ):
        with pytest.raises(api.LoginError):
            api.callback_code(url, "expected")


async def test_login_flow_does_not_fetch_callback_or_store_password(monkeypatch):
    oauth_state = None

    def authorize(method, url, kwargs):
        nonlocal oauth_state
        oauth_state = parse_qs(urlsplit(url).query)["state"][0]
        return Response(302, headers={"Location": "/u/login?state=transaction"})

    def submit(method, url, kwargs):
        assert api.origin(url) == api.AUTH_ORIGIN
        assert kwargs["data"]["password"] == "synthetic-password"
        return Response(
            302, headers={"Location": api.APP_ORIGIN + f"?state={oauth_state}&code=code"}
        )

    session = Session([authorize, Response(), submit, token_response()])
    monkeypatch.setattr(api.aiohttp, "ClientSession", lambda **kwargs: session)
    result = await api.login("synthetic@example.invalid", "synthetic-password")
    assert result.refresh_token == "new-refresh"
    assert not hasattr(result, "password")
    assert all(api.origin(url) == api.AUTH_ORIGIN for _, url, _ in session.calls)
    assert len(session.calls) == 4


async def test_login_rejects_redirect_to_untrusted_host(monkeypatch):
    session = Session([Response(302, headers={"Location": "https://evil.example/u/login"})])
    monkeypatch.setattr(api.aiohttp, "ClientSession", lambda **kwargs: session)
    with pytest.raises(api.LoginError):
        await api.login("synthetic@example.invalid", "secret")
    assert len(session.calls) == 1


async def test_rejected_login_does_not_retry_password(monkeypatch):
    session = Session(
        [Response(302, headers={"Location": "/u/login?state=t"}), Response(), Response()]
    )
    monkeypatch.setattr(api.aiohttp, "ClientSession", lambda **kwargs: session)
    with pytest.raises(api.LoginError):
        await api.login("synthetic@example.invalid", "secret")
    assert sum(call[0] == "POST" for call in session.calls) == 1


async def test_refresh_is_serialized_and_durable_before_reads():
    persist = AsyncMock()
    session = Session([token_response()])
    client = api.BlossomClient(session, api.Tokens("old-refresh"), persist)
    await asyncio.gather(*(client.ensure_token() for _ in range(8)))
    assert len(session.calls) == 1
    persist.assert_awaited_once_with("new-refresh")
    assert "new-refresh" not in repr(client.tokens)
    assert "new-access" not in repr(client.tokens)


async def test_restart_uses_saved_refresh_token():
    persisted = []

    async def save(token):
        persisted.append(token)

    client = api.BlossomClient(Session([token_response()]), api.Tokens("old"), save)
    await client.ensure_token()
    session = Session([token_response("rotated-again")])
    restarted = api.BlossomClient(session, api.Tokens(persisted[-1]), save)
    await restarted.ensure_token()
    assert session.calls[0][2]["json"]["refresh_token"] == "new-refresh"
    assert persisted[-1] == "rotated-again"


async def test_refresh_omission_retains_previous_token():
    response = Response(data={"access_token": "access", "expires_in": 3600})
    client = api.BlossomClient(Session([response]), api.Tokens("previous"))
    await client.ensure_token()
    assert client.tokens.refresh_token == "previous"


async def test_ambiguous_refresh_not_replayed_and_secrets_not_in_error():
    client = api.BlossomClient(Session([Response(error=TimeoutError("SECRET"))]), api.Tokens("old"))
    for _ in range(2):
        with pytest.raises(api.AuthError) as error:
            await client.ensure_token()
        assert "SECRET" not in str(error.value)
    assert len(client.session.calls) == 1


async def test_storage_failure_blocks_further_requests():
    persist = AsyncMock(side_effect=OSError("SECRET"))
    client = api.BlossomClient(Session([token_response()]), api.Tokens("old"), persist)
    with pytest.raises(api.AuthError, match="token_storage_failed"):
        await client.get("/users/current")
    assert len(client.session.calls) == 1


async def test_401_refreshes_once_then_auth_failure():
    session = Session([Response(401), token_response(), Response(401)])
    client = api.BlossomClient(session, api.Tokens("refresh", "access", time.monotonic() + 300))
    with pytest.raises(api.AuthError):
        await client.current_user()
    assert [call[0] for call in session.calls] == ["GET", "POST", "GET"]


async def test_api_scope_readonly_and_pagination():
    session = Session([Response(data={"data": []})])
    client = api.BlossomClient(session, api.Tokens("refresh", "access", time.monotonic() + 300))
    scope = {"member_id": "member", "installation_id": "installation", "company_id": "company"}
    assert await client.recent_sessions(scope) == []
    call = session.calls[0]
    assert call[0] == "GET"
    assert call[2]["params"] == {
        "page": 1,
        "take": 20,
        "order": "desc",
        "orderByKey": "start",
        "memberId": "member",
        "installationId": "installation",
    }
    assert call[2]["headers"]["x-selected-company"] == "company"
    assert call[2]["allow_redirects"] is False
    with pytest.raises(ValueError):
        await client.get("/optimile/home-session/start")
    assert len(session.calls) == 1


async def test_home_charging_commands_are_scoped_and_card_is_explicit():
    session = Session([Response(201, {}), Response(201, {})])
    client = api.BlossomClient(session, api.Tokens("refresh", "access", time.monotonic() + 300))
    scope = {"member_id": "member", "installation_id": "installation", "company_id": "company"}

    await client.start_home_session(scope, "selected-card")
    await client.stop_home_session(scope)

    start, stop = session.calls
    assert start[0] == stop[0] == "POST"
    assert start[1].endswith("/optimile/home-session/start")
    assert start[2]["json"] == {"cardId": "selected-card"}
    assert stop[1].endswith("/optimile/home-session/stop")
    assert "json" not in stop[2]
    assert (
        start[2]["params"]
        == stop[2]["params"]
        == {
            "memberId": "member",
            "installationId": "installation",
        }
    )
    assert start[2]["headers"]["x-selected-company"] == "company"

    with pytest.raises(ValueError):
        await client.post("/device/dangerous-command", scope)


async def test_empty_successful_command_response_is_valid():
    class EmptyResponse(Response):
        async def json(self):
            raise aiohttp.ContentTypeError(None, (), message="empty body")

    client = api.BlossomClient(
        Session([EmptyResponse(201)]),
        api.Tokens("refresh", "access", time.monotonic() + 300),
    )
    scope = {"member_id": "member", "installation_id": "installation", "company_id": "company"}
    assert await client.stop_home_session(scope) == {}


@pytest.mark.parametrize(
    "status,exception",
    [
        (403, api.PermissionError),
        (429, api.RateLimitError),
        (500, api.ConnectionError),
        (302, api.ProtocolError),
    ],
)
async def test_http_errors_are_sanitized(status, exception):
    with pytest.raises(exception) as error:
        await api.json_response(Response(status, data={"password": "SECRET"}))
    assert "SECRET" not in str(error.value)


def test_unknown_shapes_are_not_treated_as_empty():
    assert api.records({"data": []}) == []
    with pytest.raises(api.ProtocolError):
        api.records({"unexpected": []})
    with pytest.raises(api.AuthError):
        api.Tokens.from_response({"access_token": "access", "expires_in": 3600})


async def test_connection_exception_is_sanitized():
    session = Session([Response(error=aiohttp.ClientError("SECRET"))])
    client = api.BlossomClient(session, api.Tokens("r", "a", time.monotonic() + 60))
    with pytest.raises(api.ConnectionError) as error:
        await client.get("/users/current")
    assert "SECRET" not in str(error.value)


async def test_manual_requests_cannot_bypass_rate_limit():
    session = Session([Response(429, headers={"Retry-After": "120"})])
    client = api.BlossomClient(session, api.Tokens("r", "a", time.monotonic() + 300))
    for _ in range(2):
        with pytest.raises(api.RateLimitError):
            await client.current_user()
    assert len(session.calls) == 1
