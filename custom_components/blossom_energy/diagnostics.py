"""Privacy-safe diagnostics for Blossom Energy."""

from homeassistant.components.diagnostics import async_redact_data

REDACT = {"account_id", "member_id", "company_id", "installation_id", "card_id", "token_store"}


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    return {
        "config_entry": async_redact_data(dict(entry.data), REDACT),
        "last_update_success": coordinator.last_update_success,
        "session_count": len(data.get("sessions", [])),
        "card_count": len(data.get("cards", [])),
        "active_session": data.get("active_session"),
        "command_confirmation": data.get("command", {}),
    }
