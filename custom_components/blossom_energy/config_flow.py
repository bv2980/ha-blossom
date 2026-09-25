"""UI setup for the installation-only development milestone."""

from typing import Any

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN


class BlossomEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Confirm installation before adding authentication in the next milestone."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create one explicitly labelled installation-test entry."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(
                title="Blossom Energy — installation test",
                data={"installation_test": True},
            )

        return self.async_show_form(step_id="user")
