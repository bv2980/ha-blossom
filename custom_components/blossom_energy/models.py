"""Bounded, explicit mapping of the first-party session fields."""

import math
from datetime import datetime, timezone

from .api import ProtocolError


def timestamp(value):
    if not isinstance(value, str):
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except ValueError:
        return None


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else None
    except (TypeError, ValueError):
        return None


def session_summaries(rows):
    """Whitelist fields; never expose raw user/location/card objects in states."""
    result = []
    for row in rows[:20]:
        start, end = timestamp(row.get("start")), timestamp(row.get("end"))
        if start is None:
            raise ProtocolError("unknown_session_start_format")
        result.append(
            {
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "energy_kwh": number(row.get("kwh")),
                "duration_minutes": number(row.get("duration")),
                "status": str(row.get("status", "unknown"))[:40],
            }
        )
    return sorted(result, key=lambda row: row["start"], reverse=True)


def scope_choices(user):
    """Require explicit member and installation selection, never choose index 0."""
    members, installations = user.get("members"), user.get("installations")
    if not isinstance(members, list) or not isinstance(installations, list):
        raise ProtocolError("missing_account_scope")
    valid_members = {
        m["id"]: m
        for m in members
        if isinstance(m, dict)
        and isinstance(m.get("id"), str)
        and isinstance(m.get("companyId"), str)
    }
    valid_installations = {
        i["id"]: i for i in installations if isinstance(i, dict) and isinstance(i.get("id"), str)
    }
    if not valid_members or not valid_installations:
        raise ProtocolError("missing_account_scope")
    return valid_members, valid_installations
