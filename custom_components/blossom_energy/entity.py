"""Shared entity metadata for the Blossom home-charging service."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo

from .const import DOMAIN, INTEGRATION_VERSION


def device_info(entry) -> DeviceInfo:
    """Group all entities on one Home Assistant service device."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.data["installation_id"])},
        name="Blossom home charging",
        manufacturer="Blossom",
        model="Home charging service",
        sw_version=INTEGRATION_VERSION,
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://app.blossom.be",
    )
