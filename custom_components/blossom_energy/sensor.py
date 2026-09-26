"""Read-only account-scoped sensors, with bounded session summaries."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import (
    CURRENCY_EURO,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfTime,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import device_info
from .models import timestamp

PARALLEL_UPDATES = 0

CHARGER_STATES = (
    "inactive",
    "available",
    "preparing",
    "charging",
    "suspended_by_charger",
    "suspended_by_vehicle",
    "finishing",
    "reserved",
    "unavailable",
    "faulted",
    "unknown",
)
CHARGER_STATE_MAP = {
    "available": "available",
    "preparing": "preparing",
    "charging": "charging",
    "suspendedevse": "suspended_by_charger",
    "suspendedev": "suspended_by_vehicle",
    "finishing": "finishing",
    "reserved": "reserved",
    "unavailable": "unavailable",
    "faulted": "faulted",
    "inactive": "inactive",
}
COMMAND_STATES = ("idle", "pending", "confirmed", "not_confirmed", "poll_failed", "rejected")


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
            "active_session_last_update",
            "active_session_status",
            "vehicle_current",
            "vehicle_phases",
            "charger_status",
            "account",
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
        if key in (
            "last_update",
            "last_session_start",
            "last_session_end",
            "active_session_start",
            "active_session_last_update",
        ):
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        if key in ("last_session_energy", "active_session_energy"):
            self._attr_device_class = SensorDeviceClass.ENERGY
            self._attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
        if key in ("last_session_amount", "last_session_reimbursement"):
            self._attr_device_class = SensorDeviceClass.MONETARY
            self._attr_native_unit_of_measurement = CURRENCY_EURO
        if key == "charger_status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(CHARGER_STATES)
        if key == "command_status":
            self._attr_device_class = SensorDeviceClass.ENUM
            self._attr_options = list(COMMAND_STATES)
        if key == "vehicle_current":
            self._attr_device_class = SensorDeviceClass.CURRENT
            self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
        if key == "last_session_duration":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
        # Session values are not a cumulative meter; no total_increasing state class.
        if key in ("last_update", "cards", "command_status"):
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
            "active_session_last_update": timestamp(active.get("last_update")),
            "active_session_status": active.get("session_status"),
            "vehicle_current": active.get("vehicle_current"),
            "vehicle_phases": active.get("vehicle_phases"),
            "charger_status": CHARGER_STATE_MAP.get(str(data["charger_status"]).lower(), "unknown"),
            "account": data["account_label"],
            "command_status": data["command"]["state"],
        }[self.key]

    @property
    def extra_state_attributes(self):
        if self.key == "recent_sessions":
            sessions = self.coordinator.data["sessions"]
            if not self.coordinator.show_session_locations:
                sessions = [
                    {key: value for key, value in session.items() if key != "location_name"}
                    for session in sessions
                ]
            return {
                "sessions": sessions,
                "scope": "selected_member_and_installation_not_card_filtered",
                "limit": 20,
            }
        if self.key == "cards":
            return {"cards": self.coordinator.data["cards"]}
        if self.key == "selected_card":
            card_type = self.coordinator.data["selected_card_type"]
            return {
                "available": self.coordinator.data["selected_card_available"],
                "card_type": "Mobility service provider"
                if card_type.lower() == "msp"
                else card_type,
            }
        if self.key == "charger_status":
            active = self.coordinator.data["active_session_details"]
            return {
                "ocpp_status": self.coordinator.data["charger_status"],
                "session_status": active.get("session_status"),
                "vehicle_current": active.get("vehicle_current"),
                "vehicle_phases": active.get("vehicle_phases"),
            }
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
