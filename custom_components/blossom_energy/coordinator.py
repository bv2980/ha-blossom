"""One bounded poll supplies all entities and confirms charging commands."""

import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, BlossomError, PermissionError, RateLimitError
from .command_diagnostics import safe_status
from .command_history import HISTORY_AGE, requested_time, retained_history
from .const import (
    CONF_CAPTURE_COMMAND_STATUS,
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
        self.client.capture_command_status = entry.options.get(CONF_CAPTURE_COMMAND_STATUS, False)
        self.entry = entry
        self.scope = {
            key: entry.data[key] for key in ("member_id", "company_id", "installation_id")
        }
        self._command_task = None
        self.command_lock = asyncio.Lock()
        self.command_trace = {}
        self.command_history = []
        self._history_lock = asyncio.Lock()
        self._history_expiry_unsub = None
        self._history_closed = False
        self._history_storage_failed = False
        self._trace_store = Store(
            hass, 1, f"{DOMAIN}.{entry.entry_id}.command", private=True, atomic_writes=True
        )
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

    async def async_load_command_trace(self):
        """Restore historical evidence without replaying a command after restart."""
        try:
            saved = await self._trace_store.async_load()
        except Exception:
            self.command_trace = {"restore_failed": True}
            _LOGGER.warning("Could not restore charging command diagnostics")
            return
        if isinstance(saved, dict):
            # Migrate the previous single-attempt file in place; never resend a command.
            self.command_history = retained_history(saved.get("history", [saved]), dt_util.utcnow())
            for attempt in self.command_history:
                attempt.setdefault("attempt_id", uuid4().hex)
                if attempt.get("stage") in ("requesting", "confirming"):
                    attempt.update(stage="interrupted", ended_at=dt_util.utcnow().isoformat())
            self.command_trace = deepcopy(self.command_history[-1]) if self.command_history else {}
            await self._async_save_trace()

    async def async_prune_command_history(self, _now=None):
        """Expire old records even when no new commands are issued."""
        if not self._history_closed:
            await self._async_save_trace()

    async def _async_save_trace(self):
        async with self._history_lock:
            if not self._history_closed:
                await self._async_save_history_locked()

    async def _async_save_history_locked(self):
        now = dt_util.utcnow()
        rows = self.command_history
        if self.command_trace.get("attempt_id"):
            rows = [
                row for row in rows if row.get("attempt_id") != self.command_trace["attempt_id"]
            ]
            rows.append(self.command_trace)
        self.command_history = retained_history(rows, now)
        # Keep the live object: an in-flight poll may still hold a reference into it.
        if not any(
            row.get("attempt_id") == self.command_trace.get("attempt_id")
            for row in self.command_history
        ):
            self.command_trace = {}
        if self._history_expiry_unsub:
            self._history_expiry_unsub()
            self._history_expiry_unsub = None
        if self.command_history and not self._history_closed:
            expires = requested_time(self.command_history[0]) + HISTORY_AGE
            self._history_expiry_unsub = async_track_point_in_utc_time(
                self.hass, self.async_prune_command_history, expires
            )
        try:
            expected = {"history": deepcopy(self.command_history)}
            await self._trace_store.async_save(expected)
            stored = await Store(
                self.hass,
                1,
                f"{DOMAIN}.{self.entry.entry_id}.command",
                private=True,
                atomic_writes=True,
            ).async_load()
            if stored != expected:
                raise OSError("command_diagnostics_storage_failed")
            if self._history_storage_failed:
                _LOGGER.info("Charging command history storage recovered")
            self._history_storage_failed = False
        except Exception:
            self.command_trace["persistence_failed"] = True
            if not self._history_storage_failed:
                _LOGGER.warning("Could not save charging command diagnostics")
            self._history_storage_failed = True

    async def async_prepare_command(self, action, context=None):
        """Record intent before network IO; card equality never exposes identifiers."""
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
            try:
                await self._command_task
            except asyncio.CancelledError:
                pass
        if self.command_trace.get("stage") in ("requesting", "confirming"):
            self.command_trace.update(stage="superseded", ended_at=dt_util.utcnow().isoformat())
            await self._async_save_trace()
        self.client.last_command_http = {}
        self.client.last_command_status = {}
        self.command_trace = {
            "attempt_id": uuid4().hex,
            "action": action,
            "requested_at": dt_util.utcnow().isoformat(),
            "stage": "requesting",
            "selection": {
                "effective_card_matches_original": self.card_id == self.entry.data[CONF_CARD_ID],
                "effective_card_available": (self.data or {}).get("selected_card_available"),
                "submitted_card_matches_effective": True if action == "start" else None,
                "card_source": "options" if CONF_CARD_ID in self.entry.options else "entry",
            },
            "polls": [],
            "observed_before": {
                "active_session": safe_status((self.data or {}).get("active_session")),
                "device_status": safe_status((self.data or {}).get("charger_status")),
                "last_full_refresh_at": (
                    (self.data or {}).get("updated_at").isoformat()
                    if (self.data or {}).get("updated_at")
                    else None
                ),
            },
        }
        if context is not None:
            # Local HA correlation only; never store the context's user_id.
            self.command_trace["ha_context"] = {
                "id": context.id,
                "parent_id": context.parent_id,
            }
        await self._async_save_trace()

    async def _async_record_trace(self, stage):
        previous_stage = self.command_trace.get("stage")
        self.command_trace["stage"] = stage
        self.command_trace["http"] = deepcopy(self.client.last_command_http)
        self.command_trace["confirmation"] = {
            key: value.isoformat() if hasattr(value, "isoformat") else value
            for key, value in self.command.items()
        }
        _LOGGER.debug("Charging command evidence: %s", self.command_trace)
        if stage in ("confirmed", "not_confirmed", "poll_failed", "request_failed"):
            self.command_trace["ended_at"] = dt_util.utcnow().isoformat()
            if previous_stage != stage:
                log = _LOGGER.info if stage == "confirmed" else _LOGGER.warning
                log(
                    "Charging command %s (%s): %s",
                    self.command_trace.get("attempt_id"),
                    self.command_trace.get("action"),
                    stage,
                )
        await self._async_save_trace()

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
        requested = dt_util.parse_datetime(self.command_trace["requested_at"])
        self.command = {
            "action": action,
            "attempt_id": self.command_trace["attempt_id"],
            "state": "pending",
            "requested_at": requested,
            "confirmed_at": None,
            "confirmation_seconds": None,
            "poll_count": 0,
        }
        await self._async_record_trace("confirming")
        data = dict(self.data)
        data["active_session"] = "starting" if action == "start" else "stopping"
        data["command"] = dict(self.command)
        self.async_set_updated_data(data)
        self._command_task = self.hass.async_create_background_task(
            self._async_confirm_command(action, requested),
            f"{DOMAIN} confirm {action}",
            eager_start=True,
        )

    async def async_record_command_failure(self, action):
        """Expose a rejected command without retaining exception details."""
        self.command = {
            "action": action,
            "attempt_id": self.command_trace["attempt_id"],
            "state": "rejected",
            "requested_at": dt_util.parse_datetime(self.command_trace["requested_at"]),
            "confirmed_at": None,
            "confirmation_seconds": None,
            "poll_count": 0,
        }
        await self._async_record_trace("request_failed")
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
                poll = {"attempt": poll_count, "requested_at": dt_util.utcnow().isoformat()}
                self.command_trace.setdefault("polls", []).append(poll)
                try:
                    rows = await self.client.active_sessions(self.scope)
                except BlossomError as err:
                    poll["error"] = type(err).__name__
                    raise
                finally:
                    poll["completed_at"] = dt_util.utcnow().isoformat()
                poll["active_session_count"] = len(rows)
                summary = active_session_summary(rows)
                poll["device_status"] = safe_status(summary.get("device_status"))
                poll["session_status"] = safe_status(summary.get("session_status"))
                poll["session_last_update"] = summary.get("last_update")
                active = bool(rows)
                self.command["poll_count"] = poll_count
                if active == expected_active:
                    confirmed = dt_util.utcnow()
                    self.command.update(
                        state="confirmed",
                        confirmed_at=confirmed,
                        confirmation_seconds=round((confirmed - requested).total_seconds()),
                    )
                    await self._async_record_trace("confirmed")
                    await self.async_refresh()
                    return
                await self._async_record_trace("confirming")
                data = dict(self.data)
                data["command"] = dict(self.command)
                self.async_set_updated_data(data)
            self.command["state"] = "not_confirmed"
            await self._async_record_trace("not_confirmed")
            data = dict(self.data)
            data["active_session"] = "active" if not expected_active else "inactive"
            data["command"] = dict(self.command)
            self.async_set_updated_data(data)
        except asyncio.CancelledError:
            raise
        except BlossomError:
            self.command["state"] = "poll_failed"
            await self._async_record_trace("poll_failed")
            data = dict(self.data)
            data["active_session"] = "active" if data.get("active_session_details") else "inactive"
            data["command"] = dict(self.command)
            self.async_set_updated_data(data)

    async def async_shutdown(self):
        self._history_closed = True
        if self._history_expiry_unsub:
            self._history_expiry_unsub()
            self._history_expiry_unsub = None
        if self._command_task and not self._command_task.done():
            self._command_task.cancel()
            try:
                await self._command_task
            except asyncio.CancelledError:
                pass
        self.client.last_command_status = {}
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
