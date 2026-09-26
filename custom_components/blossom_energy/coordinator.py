"""One bounded poll supplies all entities and confirms charging commands."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, BlossomError, PermissionError, RateLimitError
from .const import (
    CONF_CARD_ID,
    CONF_REFRESH_INTERVAL,
    CONF_SHOW_SESSION_LOCATIONS,
    DEFAULT_REFRESH_INTERVAL,
    DOMAIN,
)
from .models import active_session_summary, member_name, scope_choices, session_summaries, timestamp

_LOGGER = logging.getLogger(__name__)


class BlossomCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, _LOGGER, name=DOMAIN, config_entry=entry)
        self.client = client
        self.entry = entry
        self.scope = {
            key: entry.data[key] for key in ("member_id", "company_id", "installation_id")
        }
        self._command_task = None
        self.update_interval = timedelta(minutes=self.normal_refresh_interval)
        self.command = {
            "action": None,
            "state": "idle",
            "requested_at": None,
            "confirmed_at": None,
            "confirmation_seconds": None,
            "poll_count": 0,
        }

    @property
    def card_id(self):
        return self.entry.options.get(CONF_CARD_ID, self.entry.data[CONF_CARD_ID])

    @property
    def normal_refresh_interval(self):
        return self.entry.options.get(CONF_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL)

    @property
    def show_session_locations(self):
        return self.entry.options.get(CONF_SHOW_SESSION_LOCATIONS, False)

    async def _async_update_data(self):
        try:
            user = await self.client.current_user()
            members, installations = scope_choices(user)
            member = members.get(self.scope["member_id"])
            if (
                user["id"] != self.entry.data["account_id"]
                or not member
                or member["companyId"] != self.scope["company_id"]
                or self.scope["installation_id"] not in installations
            ):
                raise PermissionError("scope_changed")
            cards, session_rows, active_rows = await asyncio.gather(
                self.client.cards(self.scope),
                self.client.recent_sessions(self.scope),
                self.client.active_sessions(self.scope),
            )
            sessions = session_summaries(session_rows)
            active = active_session_summary(active_rows)
            completed = [s for s in sessions if s["end"] and s["status"] != "IN_PROGRESS"]
            selected = next((c for c in cards if c["id"] == self.card_id), None)
            self.update_interval = timedelta(
                minutes=1 if active_rows else self.normal_refresh_interval
            )
            self._update_issues(selected, active)
            return {
                "cards": [
                    {
                        "id": c["id"],
                        "label": str(c.get("label", ""))[:100],
                        "type": str(c.get("type", ""))[:40],
                    }
                    for c in cards
                ],
                "sessions": sessions,
                "last_session": completed[0] if completed else {},
                "updated_at": dt_util.utcnow(),
                "selected_card_available": any(c["id"] == self.card_id for c in cards),
                "selected_card_label": str((selected or {}).get("label", ""))[:100],
                "selected_card_type": str((selected or {}).get("type", ""))[:40],
                "account_label": member_name(member),
                "active_session": "active" if active_rows else "inactive",
                "active_session_details": active,
                "charger_status": active.get("device_status") or "inactive",
                "active_session_schema": _safe_schema(active_rows),
                "command": dict(self.command),
            }
        except AuthError as err:
            raise ConfigEntryAuthFailed("Blossom requires a new sign-in") from err
        except RateLimitError as err:
            raise UpdateFailed("Blossom rate limit", retry_after=err.seconds) from err
        except BlossomError as err:
            raise UpdateFailed(str(err)) from err

    async def async_begin_confirmation(self, action):
        """Expose a pending command and confirm it for at most one minute."""
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
        requested = dt_util.utcnow()
        self.command = {
            "action": action,
            "state": "pending",
            "requested_at": requested,
            "confirmed_at": None,
            "confirmation_seconds": None,
            "poll_count": 0,
        }
        data = dict(self.data)
        data["active_session"] = "starting" if action == "start" else "stopping"
        data["command"] = dict(self.command)
        self.async_set_updated_data(data)
        self._command_task = self.hass.async_create_background_task(
            self._async_confirm_command(action, requested),
            f"{DOMAIN} confirm {action}",
            eager_start=True,
        )

    def async_record_command_failure(self, action):
        """Expose a rejected command without retaining exception details."""
        self.command = {
            "action": action,
            "state": "rejected",
            "requested_at": dt_util.utcnow(),
            "confirmed_at": None,
            "confirmation_seconds": None,
            "poll_count": 0,
        }
        data = dict(self.data)
        data["command"] = dict(self.command)
        self.async_set_updated_data(data)

    def _update_issues(self, selected, active):
        card_issue = f"selected_card_missing_{self.entry.entry_id}"
        if selected:
            ir.async_delete_issue(self.hass, DOMAIN, card_issue)
        else:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                card_issue,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="selected_card_missing",
            )

        stale_issue = f"active_session_stale_{self.entry.entry_id}"
        last_update = timestamp(active.get("last_update"))
        is_stale = last_update is not None and dt_util.utcnow() - last_update > timedelta(
            minutes=10
        )
        if is_stale:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                stale_issue,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="active_session_stale",
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, stale_issue)

    async def _async_confirm_command(self, action, requested):
        expected_active = action == "start"
        try:
            for poll_count in range(1, 7):
                await asyncio.sleep(10)
                active = bool(await self.client.active_sessions(self.scope))
                self.command["poll_count"] = poll_count
                if active == expected_active:
                    confirmed = dt_util.utcnow()
                    self.command.update(
                        state="confirmed",
                        confirmed_at=confirmed,
                        confirmation_seconds=round((confirmed - requested).total_seconds()),
                    )
                    await self.async_refresh()
                    return
                data = dict(self.data)
                data["command"] = dict(self.command)
                self.async_set_updated_data(data)
            self.command["state"] = "not_confirmed"
            data = dict(self.data)
            data["active_session"] = "active" if not expected_active else "inactive"
            data["command"] = dict(self.command)
            self.async_set_updated_data(data)
        except asyncio.CancelledError:
            raise
        except BlossomError:
            self.command["state"] = "poll_failed"
            data = dict(self.data)
            data["command"] = dict(self.command)
            self.async_set_updated_data(data)

    async def async_shutdown(self):
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
        await super().async_shutdown()


def _safe_schema(rows):
    """Expose field names, never values, to diagnose upstream schema changes."""
    if not rows:
        return {
            "field_count": 0,
            "field_names": [],
            "session_field_count": 0,
            "session_field_names": [],
        }

    def names(value):
        if not isinstance(value, dict):
            return []
        return sorted(
            key[:80] for key in value if isinstance(key, str) and key.replace("_", "").isalnum()
        )[:50]

    row = rows[0]
    session = row.get("session")
    return {
        "field_count": len(row),
        "field_names": names(row),
        "session_field_count": len(session) if isinstance(session, dict) else 0,
        "session_field_names": names(session),
    }
