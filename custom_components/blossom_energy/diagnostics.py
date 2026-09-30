"""Privacy-safe diagnostics for Blossom Energy."""

from copy import deepcopy

from homeassistant.components.diagnostics import async_redact_data

from .command_diagnostics import safe_status
from .const import CONF_CAPTURE_COMMAND_STATUS

REDACT = {
    "account_id",
    "member_id",
    "company_id",
    "installation_id",
    "card_id",
    "card_label",
    "token_store",
}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    await coordinator.async_prune_command_history()
    data = coordinator.data or {}
    return {
        "config_entry": async_redact_data(dict(entry.data), REDACT),
        "last_update_success": coordinator.last_update_success,
        "session_count": len(data.get("sessions", [])),
        "card_count": len(data.get("cards", [])),
        "active_session": data.get("active_session"),
        "refresh_interval_minutes": coordinator.normal_refresh_interval,
        "active_refresh": data.get("active_session") in ("active", "stopping"),
        "session_locations_enabled": coordinator.show_session_locations,
        "active_session_schema": data.get("active_session_schema", {}),
        "command_confirmation": data.get("command", {}),
        "last_command_attempt": deepcopy(coordinator.command_trace),
        "command_history": list(reversed(deepcopy(coordinator.command_history))),
        "command_history_retention": {"max_attempts": 20, "max_age_days": 7},
        "command_history_storage_failed": coordinator._history_storage_failed,
        "exact_command_status": {
            "enabled": entry.options.get(CONF_CAPTURE_COMMAND_STATUS, False),
            "capture": dict(coordinator.client.last_command_status)
            if entry.options.get(CONF_CAPTURE_COMMAND_STATUS, False)
            else {},
            "retention": "memory_only_until_next_command_or_reload",
        },
        "actual_refresh_interval_seconds": coordinator.update_interval.total_seconds(),
        "last_full_refresh_at": data.get("updated_at"),
        "active_session_details": {
            key: safe_status(value) if key in ("device_status", "session_status") else value
            for key, value in data.get("active_session_details", {}).items()
            if key
            in (
                "device_status",
                "session_status",
                "last_update",
                "start",
                "energy_kwh",
                "vehicle_current",
                "vehicle_phases",
            )
        },
    }
