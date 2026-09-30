"""Strictly allowlisted command evidence; never retain raw response bodies or IDs."""

import json

MAX_BODY_BYTES = 16384
SAFE_VALUES = {
    "accepted",
    "rejected",
    "pending",
    "success",
    "failed",
    "error",
    "ok",
    "authorized",
    "unauthorized",
    "blocked",
    "invalid",
    "expired",
    "concurrenttx",
    "charging",
    "available",
    "preparing",
    "suspendedev",
    "suspendedevse",
    "finishing",
    "reserved",
    "unavailable",
    "faulted",
    "in_progress",
    "finished",
    "started",
    "stopped",
    "starting",
    "stopping",
    "active",
    "inactive",
    "not_supported",
    "not_found",
    "offline",
    "online",
    "timeout",
}


def safe_status(value):
    """Unknown strings might contain personal data, even under a status key."""
    if value is None:
        return None
    if isinstance(value, str) and value.lower() in SAFE_VALUES:
        return value.lower()
    return "unrecognized"


def response_summary(body):
    """Report only known result fields and enums, including common nested envelopes."""
    if len(body) > MAX_BODY_BYTES:
        return {"body": "too_large"}
    if not body.strip():
        return {"body": "empty"}
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return {"body": "non_json"}
    result = {"body": "json", "results": {}}

    def visit(value, prefix="", depth=0):
        if not isinstance(value, dict):
            if prefix:
                result["results"][prefix] = safe_status(value)
            return
        for key in ("success", "accepted", "status", "code", "error", "result", "data"):
            if key not in value:
                continue
            item = value[key]
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(item, dict) and depth < 2:
                visit(item, name, depth + 1)
            elif type(item) is bool:
                result["results"][name] = item
            elif key == "code" and type(item) is int and 100 <= item <= 599:
                result["results"][name] = item
            else:
                result["results"][name] = safe_status(item)

    visit(payload)
    return result


async def read_response_summary(response):
    """Bound memory use without exposing headers, URLs, or arbitrary response text."""
    body = bytearray()
    while len(body) <= MAX_BODY_BYTES:
        chunk = await response.content.read(min(4096, MAX_BODY_BYTES + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    return response_summary(bytes(body))
