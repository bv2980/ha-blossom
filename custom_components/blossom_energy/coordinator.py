"""One bounded poll supplies all entities."""

import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import AuthError, BlossomError, PermissionError, RateLimitError
from .const import DOMAIN
from .models import scope_choices, session_summaries

_LOGGER = logging.getLogger(__name__)


class BlossomCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(
            hass, _LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(minutes=15)
        )
        self.client = client
        self.entry = entry
        self.scope = {
            key: entry.data[key] for key in ("member_id", "company_id", "installation_id")
        }

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
            cards = await self.client.cards(self.scope)
            sessions = session_summaries(await self.client.recent_sessions(self.scope))
            active_sessions = await self.client.active_sessions(self.scope)
            completed = [s for s in sessions if s["end"] and s["status"] != "IN_PROGRESS"]
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
                "selected_card_available": any(
                    c["id"] == self.entry.data["card_id"] for c in cards
                ),
                "active_session": "active" if active_sessions else "inactive",
            }
        except AuthError as err:
            raise ConfigEntryAuthFailed("Blossom requires a new sign-in") from err
        except RateLimitError as err:
            raise UpdateFailed("Blossom rate limit", retry_after=err.seconds) from err
        except BlossomError as err:
            raise UpdateFailed(str(err)) from err
