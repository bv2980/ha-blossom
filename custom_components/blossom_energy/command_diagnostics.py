"""Strictly allowlisted command evidence; never retain raw response bodies or IDs."""

import json
import re

MAX_BODY_BYTES = 16384
MAX_RESULT_FIELDS = 50
MAX_ARRAY_ITEMS = 3
RESULT_KEYS = ("success", "accepted", "status", "code", "error", "result", "data")
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
    "notsupported",
    "notauthorized",
    "not_authorized",
    "invalidtoken",
    "invalid_token",
    "occupied",
    "inoperative",
    "evdisconnected",
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
    result = {"body": "json", "results": {}, "value_details": {}}

    def visit(value, prefix="response", depth=0, key="status"):
        # Paths contain only our fixed keys and bounded array indices, never API keys.
        if len(result["value_details"]) >= MAX_RESULT_FIELDS:
            result["truncated"] = True
            return
        detail = {
            "type": "null"
            if value is None
            else {
                dict: "object",
                list: "array",
                str: "string",
                bool: "boolean",
                int: "integer",
                float: "number",
            }.get(type(value), "unknown")
        }
        result["value_details"][prefix] = detail
        if isinstance(value, (dict, list)):
            detail["count"] = len(value)
            if depth >= 4:
                detail["truncated"] = True
                return
            if isinstance(value, dict):
                detail["omitted_field_count"] = sum(name not in RESULT_KEYS for name in value)
                for name in RESULT_KEYS:
                    if name in value:
                        path = name if prefix == "response" else f"{prefix}.{name}"
                        visit(value[name], path, depth + 1, name)
            else:
                detail["truncated"] = len(value) > MAX_ARRAY_ITEMS
                for index, item in enumerate(value[:MAX_ARRAY_ITEMS]):
                    visit(item, f"{prefix}[{index}]", depth + 1, key)
            return
        if type(value) is bool or value is None:
            result["results"][prefix] = value
            return
        # Restrict numbers to small status/code values; IDs and arbitrary numbers stay private.
        numeric = value
        if isinstance(value, str):
            detail["length"] = len(value)
            if (
                len(value) <= 4
                and value.removeprefix("-").isascii()
                and value.removeprefix("-").isdigit()
            ):
                numeric = int(value)
        if key in ("status", "code") and type(numeric) is int and -1 <= numeric <= 599:
            result["results"][prefix] = numeric
        else:
            result["results"][prefix] = safe_status(value)

    visit(payload)
    return result


def exact_status_evidence(body, protected_values=()):
    """Opt-in, memory-only top-level status; never return the rest of the payload."""
    if len(body) > MAX_BODY_BYTES:
        return {"state": "body_too_large"}
    try:
        payload = json.loads(body)
    except (ValueError, UnicodeError, RecursionError):
        return {"state": "not_json"}
    if not isinstance(payload, dict) or "status" not in payload:
        return {"state": "status_missing"}
    value = payload["status"]
    if not isinstance(value, str):
        return {"state": "not_text"}
    if not 1 <= len(value) <= 128:
        return {"state": "text_outside_limit"}
    # Do not export obvious credentials, addresses or known request identifiers.
    if (
        any(secret and str(secret).casefold() in value.casefold() for secret in protected_values)
        or re.search(r"[@:/\\\x00-\x1f\x7f]|bearer|password|token|secret", value, re.I)
        or re.search(r"[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]+|[0-9a-f]{8}-[0-9a-f-]{27,}", value, re.I)
    ):
        return {"state": "sensitive_text_withheld"}
    return {"state": "captured", "value": value}


async def read_response_summary(response, *, status_capture=None, protected_values=()):
    """Bound memory use without exposing headers, URLs, or arbitrary response text."""
    body = bytearray()
    while len(body) <= MAX_BODY_BYTES:
        chunk = await response.content.read(min(4096, MAX_BODY_BYTES + 1 - len(body)))
        if not chunk:
            break
        body.extend(chunk)
    if status_capture is not None:
        status_capture(exact_status_evidence(bytes(body), protected_values))
    return response_summary(bytes(body))
