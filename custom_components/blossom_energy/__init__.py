"""Blossom Energy integration: installation-only development milestone."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load the installation test; no API resources exist at this milestone."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the installation test; no resources need cleanup yet."""
    return True
