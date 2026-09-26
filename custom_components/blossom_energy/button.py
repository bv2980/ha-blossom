"""Manual refresh and explicit home-charging controls."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import BlossomError
from .entity import device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            RefreshButton(entry.runtime_data),
            ChargingButton(entry.runtime_data, "start_charging"),
            ChargingButton(entry.runtime_data, "stop_charging"),
        ]
    )


class RefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_refresh"
        self._attr_device_info = device_info(coordinator.entry)

    async def async_press(self):
        await self.coordinator.async_request_refresh()


class ChargingButton(CoordinatorEntity, ButtonEntity):
    """Explicit start or stop control for the selected home installation."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, action):
        super().__init__(coordinator)
        self.action = action
        self._attr_translation_key = action
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{action}"
        self._attr_device_info = device_info(coordinator.entry)

    @property
    def available(self):
        if not super().available:
            return False
        state = self.coordinator.data["active_session"]
        if state in ("starting", "stopping"):
            return False
        active = state == "active"
        return active if self.action == "stop_charging" else not active

    async def async_press(self):
        try:
            if self.action == "start_charging":
                await self.coordinator.client.start_home_session(
                    self.coordinator.scope, self.coordinator.entry.data["card_id"]
                )
            else:
                await self.coordinator.client.stop_home_session(self.coordinator.scope)
        except BlossomError as err:
            self.coordinator.async_record_command_failure(
                "start" if self.action == "start_charging" else "stop"
            )
            raise HomeAssistantError("Blossom rejected the charging command") from err
        await self.coordinator.async_begin_confirmation(
            "start" if self.action == "start_charging" else "stop"
        )
