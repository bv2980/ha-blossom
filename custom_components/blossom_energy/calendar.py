"""Read-only calendar view of the bounded recent Blossom sessions."""

from datetime import timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .entity import device_info
from .models import timestamp

PARALLEL_UPDATES = 0

TEXT = {
    "en": {
        "home": "Home",
        "public": "Public",
        "session": "Charging session",
        "duration": "Duration",
        "amount": "Amount",
        "reimbursement": "Home reimbursement",
        "status": "Status",
        "active": "Active session; end time is provisional",
        "in_progress": "In progress",
        "finished": "Finished",
        "completed": "Completed",
    },
    "nl": {
        "home": "Thuis",
        "public": "Publiek",
        "session": "Laadsessie",
        "duration": "Duur",
        "amount": "Bedrag",
        "reimbursement": "Thuisvergoeding",
        "status": "Status",
        "active": "Actieve sessie; eindtijd is voorlopig",
        "in_progress": "Bezig",
        "finished": "Voltooid",
        "completed": "Voltooid",
    },
}


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
        if self.coordinator.data["active_session"] not in ("active", "stopping"):
            return None
        active_start = self.coordinator.data["active_session_details"].get("start")
        session = next(
            (
                item
                for item in self.coordinator.data["sessions"]
                if item.get("start") == active_start
                or str(item.get("status", "")).upper() == "IN_PROGRESS"
            ),
            None,
        )
        if session is None:
            active = self.coordinator.data["active_session_details"]
            session = {
                "start": active.get("start"),
                "energy_kwh": active.get("energy_kwh"),
                "status": active.get("session_status") or "IN_PROGRESS",
                "type": "Home",
            }
        return self._event(session, active=True)

    async def async_get_events(self, hass, start_date, end_date):
        current = self.event
        current_start = current.start if current else None
        events = [
            self._event(session, active=timestamp(session.get("start")) == current_start)
            for session in self.coordinator.data["sessions"]
        ]
        if current and not any(event and event.start == current.start for event in events):
            events.append(current)
        return [
            event
            for event in events
            if event is not None and event.end > start_date and event.start < end_date
        ]

    def _event(self, session, active=False):
        start = timestamp(session.get("start"))
        if start is None:
            return None
        end = timestamp(session.get("end"))
        if active:
            end = dt_util.utcnow() + timedelta(minutes=2)
        elif end is None:
            duration = session.get("duration_minutes") or 1
            end = start + timedelta(minutes=duration)
        energy = session.get("energy_kwh")
        text = self._text
        session_type = str(session.get("type") or "").lower()
        summary = text.get(session_type, session.get("type") or text["session"])
        if energy is not None:
            summary += f" · {energy:.2f} kWh"
        details = []
        if session.get("duration_minutes") is not None:
            details.append(f"{text['duration']}: {session['duration_minutes']:.0f} min")
        if session.get("amount_eur") is not None:
            details.append(f"{text['amount']}: €{session['amount_eur']:.2f}")
        if session.get("home_reimbursement_eur") is not None:
            details.append(f"{text['reimbursement']}: €{session['home_reimbursement_eur']:.2f}")
        if session.get("status"):
            status = str(session["status"])
            details.append(f"{text['status']}: {text.get(status.lower(), status)}")
        if active:
            details.append(text["active"])
        return CalendarEvent(
            start=start,
            end=end,
            summary=summary,
            description="\n".join(details) or None,
            location=session.get("location_name")
            if self.coordinator.show_session_locations
            else None,
        )

    @property
    def _text(self):
        language = str(self.coordinator.hass.config.language or "en").split("-")[0]
        return TEXT.get(language, TEXT["en"])
