"""Manual data refresh; deliberately no charging command."""

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RefreshButton(entry.runtime_data)])


class RefreshButton(CoordinatorEntity, ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_refresh"

    async def async_press(self):
        await self.coordinator.async_request_refresh()
