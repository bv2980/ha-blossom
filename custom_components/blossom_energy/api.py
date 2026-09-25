"""Asynchronous Blossom client with an explicit endpoint allowlist.

Personal login follows the first-party web application's Auth0 PKCE flow.
This is not a documented third-party authentication contract. Only the Auth0
host may receive credentials; redirects to the app are inspected, never fetched.
"""

import asyncio
import base64
import hashlib
import math
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import aiohttp

AUTH_ORIGIN = "https://blossom-production.eu.auth0.com"
APP_ORIGIN = "https://app.blossom.be"
API_ORIGIN = "https://api.blossom.be/api"
CLIENT_ID = "RTofmsbiLPSlisRHtIFohGRPBcGgrIrs"
TIMEOUT = aiohttp.ClientTimeout(total=20, connect=10)
READ_PATHS = {
    "/users/current",
    "/optimile/home-session/cards",
    "/charging-session/employee/recent",
    "/charging-session/employee/active",
}


class BlossomError(Exception):
    """Sanitized failure, without URLs, response bodies or credentials."""


class AuthError(BlossomError):
    """Fresh authentication is required."""


class LoginError(AuthError):
    """Login rejected, or an interactive challenge is required."""


class ConnectionError(BlossomError):
    """Temporary network error."""


class ProtocolError(BlossomError):
    """Unsupported upstream response or account shape."""


class PermissionError(BlossomError):
    """Account lacks access to the chosen scope."""


class RateLimitError(BlossomError):
    """Upstream asked us to wait."""

    def __init__(self, seconds=300):
        self.seconds = seconds
        super().__init__("rate_limited")


@dataclass(repr=False)
class Tokens:
    """Secrets never participate in repr/log output."""

    refresh_token: str = field(repr=False)
    access_token: str = field(default="", repr=False)
    expires_at: float = 0

    @classmethod
    def from_response(cls, data, previous_refresh=""):
        if not isinstance(data, dict):
            raise ProtocolError("invalid_token_response")
        access = data.get("access_token")
        refresh = data.get("refresh_token") or previous_refresh
        try:
            lifetime = float(data["expires_in"])
        except (KeyError, TypeError, ValueError):
            raise ProtocolError("invalid_token_expiry") from None
        if not isinstance(access, str) or not access:
            raise ProtocolError("missing_access_token")
        if not isinstance(refresh, str) or not refresh:
            raise AuthError("missing_refresh_token")
        if not math.isfinite(lifetime) or lifetime <= 0:
            raise ProtocolError("invalid_token_expiry")
        return cls(refresh, access, time.monotonic() + lifetime - min(60, lifetime / 10))


def pkce_pair():
    """Generate an RFC 7636 S256 verifier/challenge pair."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge.rstrip(b"=").decode()


def origin(url):
    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def callback_code(url, expected_state):
    """Validate redirect destination and OAuth state before exchanging code."""
    parsed = urlsplit(url)
    if origin(url) != APP_ORIGIN or parsed.path not in ("", "/") or parsed.fragment:
        raise LoginError("unexpected_callback")
    query = parse_qs(parsed.query)
    states, codes = query.get("state", []), query.get("code", [])
    if len(states) != 1 or not secrets.compare_digest(states[0], expected_state):
        raise LoginError("invalid_oauth_state")
    if "error" in query or len(codes) != 1:
        raise LoginError("login_requires_attention")
    return codes[0]


async def json_response(response, *, token=False):
    """Classify errors without exposing the upstream body."""
    if response.status == 429:
        try:
            seconds = max(60, min(3600, int(response.headers.get("Retry-After", "300"))))
        except ValueError:
            seconds = 300
        raise RateLimitError(seconds)
    if response.status == 401 or (token and response.status in (400, 403)):
        raise AuthError("authentication_failed")
    if response.status == 403:
        raise PermissionError("scope_denied")
    if response.status >= 500:
        raise ConnectionError("upstream_unavailable")
    if response.status < 200 or response.status >= 300:
        raise ProtocolError("unexpected_http_status")
    try:
        return await response.json()
    except (ValueError, aiohttp.ContentTypeError):
        raise ProtocolError("invalid_json") from None


async def login(email: str, password: str) -> Tokens:
    """Use a short-lived isolated cookie jar; never retain the password."""
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    authorize = (
        AUTH_ORIGIN
        + "/authorize?"
        + urlencode(
            {
                "client_id": CLIENT_ID,
                "response_type": "code",
                "redirect_uri": APP_ORIGIN,
                "scope": "openid profile email offline_access",
                "audience": AUTH_ORIGIN + "/api/v2/",
                "state": state,
                "nonce": secrets.token_urlsafe(32),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    try:
        async with asyncio.timeout(60), aiohttp.ClientSession(timeout=TIMEOUT) as session:
            current = authorize
            form_sent = False
            method, form = "GET", None
            for _ in range(12):
                if origin(current) == APP_ORIGIN:
                    code = callback_code(current, state)
                    async with session.post(
                        AUTH_ORIGIN + "/oauth/token",
                        json={
                            "grant_type": "authorization_code",
                            "client_id": CLIENT_ID,
                            "code_verifier": verifier,
                            "code": code,
                            "redirect_uri": APP_ORIGIN,
                        },
                        allow_redirects=False,
                    ) as response:
                        return Tokens.from_response(await json_response(response, token=True))
                if origin(current) != AUTH_ORIGIN:
                    raise LoginError("unexpected_login_host")
                async with session.request(
                    method, current, data=form, allow_redirects=False
                ) as response:
                    if response.status in (301, 302, 303):
                        location = response.headers.get("Location")
                        if not location:
                            raise LoginError("missing_redirect")
                        current = urljoin(current, location)
                        method, form = "GET", None
                        continue
                    # Do not replay a password POST across a 307/308 redirect.
                    if response.status == 429:
                        raise RateLimitError()
                    if response.status >= 500:
                        raise ConnectionError("login_unavailable")
                    parsed = urlsplit(current)
                    txn = parse_qs(parsed.query).get("state", [])
                    if (
                        response.status != 200
                        or parsed.path != "/u/login"
                        or form_sent
                        or len(txn) != 1
                    ):
                        raise LoginError("login_requires_attention")
                    # Load the form to establish cookies; no HTML or response logging.
                    await response.read()
                    form = {"state": txn[0], "username": email, "password": password}
                    method, form_sent = "POST", True
            raise LoginError("too_many_redirects")
    except (aiohttp.ClientError, TimeoutError):
        raise ConnectionError("login_connection_failed") from None


def records(payload):
    """Accept the observed list and paginated {data: [...]} contracts only."""
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ProtocolError("unexpected_list_response")
    return rows


class BlossomClient:
    """One token lock per account client; runtime shares HA's HTTP session."""

    def __init__(
        self, session, tokens: Tokens, persist: Callable[[str], Awaitable[None]] | None = None
    ):
        self.session, self.tokens, self.persist = session, tokens, persist
        self._token_lock = asyncio.Lock()
        self._retry_at = 0.0

    def _check_backoff(self):
        remaining = self._retry_at - time.monotonic()
        if remaining > 0:
            raise RateLimitError(math.ceil(remaining))

    async def ensure_token(self, rejected_token=None):
        async with self._token_lock:
            self._check_backoff()
            if self.tokens.access_token and time.monotonic() < self.tokens.expires_at:
                if rejected_token is None or rejected_token != self.tokens.access_token:
                    return
            if not self.tokens.refresh_token:
                raise AuthError("reauth_required")
            try:
                async with self.session.post(
                    AUTH_ORIGIN + "/oauth/token",
                    json={
                        "grant_type": "refresh_token",
                        "client_id": CLIENT_ID,
                        "refresh_token": self.tokens.refresh_token,
                    },
                    timeout=TIMEOUT,
                    allow_redirects=False,
                ) as response:
                    data = await json_response(response, token=True)
                updated = Tokens.from_response(data, self.tokens.refresh_token)
            except RateLimitError as err:
                self._retry_at = time.monotonic() + err.seconds
                raise
            except (aiohttp.ClientError, TimeoutError):
                # Rotation may already have consumed the token: no automatic replay.
                self.tokens = Tokens("")
                raise AuthError("refresh_outcome_unknown") from None
            self.tokens = updated
            if self.persist:
                try:
                    await self.persist(updated.refresh_token)
                except Exception:
                    self.tokens = Tokens("")
                    raise AuthError("token_storage_failed") from None

    async def get(self, path, scope=None, params=None):
        if path not in READ_PATHS:
            raise ValueError("Only explicitly allowed read endpoints are supported")
        await self.ensure_token()
        for attempt in range(2):
            access = self.tokens.access_token
            headers = {"Authorization": f"Bearer {access}"}
            query = dict(params or {})
            if scope:
                query.update(memberId=scope["member_id"], installationId=scope["installation_id"])
                headers.update(
                    {
                        "x-selected-company": scope["company_id"],
                        "x-hrzn-skip-warning": "Robbe is cool",
                    }
                )
            try:
                async with self.session.get(
                    API_ORIGIN + path,
                    params=query,
                    headers=headers,
                    timeout=TIMEOUT,
                    allow_redirects=False,
                ) as response:
                    if response.status == 401 and attempt == 0:
                        await self.ensure_token(rejected_token=access)
                        continue
                    return await json_response(response)
            except RateLimitError as err:
                self._retry_at = time.monotonic() + err.seconds
                raise
            except (aiohttp.ClientError, TimeoutError):
                raise ConnectionError("api_connection_failed") from None
        raise AuthError("authentication_failed")

    async def post(self, path, scope, data=None):
        """Send one explicitly allowlisted home-charging command."""
        if path not in {"/optimile/home-session/start", "/optimile/home-session/stop"}:
            raise ValueError("Only explicitly allowed command endpoints are supported")
        await self.ensure_token()
        for attempt in range(2):
            access = self.tokens.access_token
            headers = {
                "Authorization": f"Bearer {access}",
                "x-selected-company": scope["company_id"],
                "x-hrzn-skip-warning": "Robbe is cool",
            }
            params = {
                "memberId": scope["member_id"],
                "installationId": scope["installation_id"],
            }
            request_data = {"json": data} if data is not None else {}
            try:
                async with self.session.post(
                    API_ORIGIN + path,
                    params=params,
                    headers=headers,
                    timeout=TIMEOUT,
                    allow_redirects=False,
                    **request_data,
                ) as response:
                    if response.status == 401 and attempt == 0:
                        await self.ensure_token(rejected_token=access)
                        continue
                    return await json_response(response)
            except RateLimitError as err:
                self._retry_at = time.monotonic() + err.seconds
                raise
            except (aiohttp.ClientError, TimeoutError):
                raise ConnectionError("api_connection_failed") from None
        raise AuthError("authentication_failed")

    async def current_user(self):
        data = await self.get("/users/current")
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise ProtocolError("missing_account_identity")
        return data

    async def cards(self, scope):
        cards = records(await self.get("/optimile/home-session/cards", scope))
        if any(not isinstance(c.get("id"), str) for c in cards):
            raise ProtocolError("invalid_cards")
        return cards

    async def recent_sessions(self, scope):
        return records(
            await self.get(
                "/charging-session/employee/recent",
                scope,
                {"page": 1, "take": 20, "order": "desc", "orderByKey": "start"},
            )
        )[:20]

    async def active_sessions(self, scope):
        return records(await self.get("/charging-session/employee/active", scope))

    async def start_home_session(self, scope, card_id):
        return await self.post("/optimile/home-session/start", scope, {"cardId": card_id})

    async def stop_home_session(self, scope):
        return await self.post("/optimile/home-session/stop", scope)
