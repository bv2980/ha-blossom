"""Automation-friendly Blossom session state."""

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import device_info

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ActiveSessionBinarySensor(entry.runtime_data)])


class ActiveSessionBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """True only after Blossom reports an active home session."""

    _attr_has_entity_name = True
    _attr_translation_key = "active_session"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_active_session_binary"
        self._attr_device_info = device_info(coordinator.entry)

    @property
    def is_on(self):
        return self.coordinator.data["active_session"] in ("active", "stopping")
