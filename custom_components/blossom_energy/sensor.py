"""Read-only account-scoped sensors, with bounded session summaries."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import device_info
from .models import timestamp

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        BlossomSensor(entry.runtime_data, key)
        for key in (
            "last_update",
            "cards",
            "recent_sessions",
            "last_session_start",
            "last_session_energy",
            "last_session_duration",
            "selected_card",
            "active_session",
        )
    )


class BlossomSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key):
        super().__init__(coordinator)
        self.key = key
        self._attr_unique_id = f"{coordinator.entry.unique_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = device_info(coordinator.entry)
        if key in ("last_update", "last_session_start"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key == "last_session_energy":
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        if key == "last_session_duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        # Session values are not a cumulative meter; no total_increasing state class.
        if key in ("last_update", "cards", "selected_card"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        data = self.coordinator.data
        last = data["last_session"]
        return {
            "last_update": data["updated_at"],
            "cards": len(data["cards"]),
            "recent_sessions": len(data["sessions"]),
            "last_session_start": timestamp(last.get("start")),
            "last_session_energy": last.get("energy_kwh"),
            "last_session_duration": last.get("duration_minutes"),
            "selected_card": self.coordinator.entry.data["card_label"],
            "active_session": data["active_session"],
        }[self.key]

    @property
    def extra_state_attributes(self):
        if self.key == "recent_sessions":
            return {
                "sessions": self.coordinator.data["sessions"],
                "scope": "selected_member_and_installation_not_card_filtered",
                "limit": 20,
            }
        if self.key == "cards":
            return {"cards": self.coordinator.data["cards"]}
        if self.key == "selected_card":
            return {"available": self.coordinator.data["selected_card_available"]}
        return None
