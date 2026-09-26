"""Read-only calendar view of the bounded recent Blossom sessions."""

from datetime import timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .entity import device_info
from .models import timestamp

PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ChargingSessionsCalendar(entry.runtime_data)])


class ChargingSessionsCalendar(CoordinatorEntity, CalendarEntity):
    """Expose recent sessions without creating one entity per session."""

    _attr_has_entity_name = True
    _attr_translation_key = "charging_sessions"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.unique_id}_charging_sessions"
        self._attr_device_info = device_info(coordinator.entry)

    @property
    def event(self):
        return None

    async def async_get_events(self, hass, start_date, end_date):
        events = [self._event(session) for session in self.coordinator.data["sessions"]]
        return [
            event
            for event in events
            if event is not None and event.end > start_date and event.start < end_date
        ]

    def _event(self, session):
        start = timestamp(session.get("start"))
        if start is None:
            return None
        end = timestamp(session.get("end"))
        if end is None:
            duration = session.get("duration_minutes") or 1
            end = start + timedelta(minutes=duration)
        energy = session.get("energy_kwh")
        summary = str(session.get("type") or "Charging session")
        if energy is not None:
            summary += f" · {energy:.2f} kWh"
        details = []
        if session.get("duration_minutes") is not None:
            details.append(f"Duration: {session['duration_minutes']:.0f} min")
        if session.get("amount_eur") is not None:
            details.append(f"Amount: €{session['amount_eur']:.2f}")
        if session.get("home_reimbursement_eur") is not None:
            details.append(f"Home reimbursement: €{session['home_reimbursement_eur']:.2f}")
        if session.get("status"):
            details.append(f"Status: {session['status']}")
        return CalendarEvent(
            start=start,
            end=end,
            summary=summary,
            description="\n".join(details) or None,
            location=session.get("location_name")
            if self.coordinator.show_session_locations
            else None,
        )
