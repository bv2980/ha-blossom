"""Read-only account-scoped sensors, with bounded session summaries."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import CURRENCY_EURO, EntityCategory, UnitOfEnergy, UnitOfTime
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
            "last_session_end",
            "last_session_type",
            "last_session_amount",
            "last_session_reimbursement",
            "selected_card",
            "active_session",
            "active_session_start",
            "active_session_energy",
            "command_status",
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
        if key in ("last_update", "last_session_start", "last_session_end", "active_session_start"):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key in ("last_session_energy", "active_session_energy"):
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        if key in ("last_session_amount", "last_session_reimbursement"):
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = CURRENCY_EURO
        if key == "last_session_duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        # Session values are not a cumulative meter; no total_increasing state class.
        if key in ("last_update", "cards", "selected_card", "command_status"):
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self):
        data = self.coordinator.data
        last = data["last_session"]
        active = data["active_session_details"]
        return {
            "last_update": data["updated_at"],
            "cards": len(data["cards"]),
            "recent_sessions": len(data["sessions"]),
            "last_session_start": timestamp(last.get("start")),
            "last_session_energy": last.get("energy_kwh"),
            "last_session_duration": last.get("duration_minutes"),
            "last_session_end": timestamp(last.get("end")),
            "last_session_type": last.get("type"),
            "last_session_amount": last.get("amount_eur"),
            "last_session_reimbursement": last.get("home_reimbursement_eur"),
            "selected_card": data["selected_card_label"],
            "active_session": data["active_session"],
            "active_session_start": timestamp(active.get("start")),
            "active_session_energy": active.get("energy_kwh"),
            "command_status": data["command"]["state"],
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
        if self.key in ("last_session_amount", "last_session_reimbursement"):
            last = self.coordinator.data["last_session"]
            return {
                "session_type": last.get("type"),
                "public_price_ex_vat_eur": last.get("public_price_ex_vat_eur"),
                "vat_percentage": last.get("vat_percentage"),
            }
        if self.key == "command_status":
            return self.coordinator.data["command"]
        return None
