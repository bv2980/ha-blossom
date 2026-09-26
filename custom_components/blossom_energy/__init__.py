"""Blossom Energy integration setup."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BlossomClient, Tokens
from .coordinator import BlossomCoordinator
from .storage import save_refresh_token, token_store

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load credentials, refresh data once, then set up entities."""
    if entry.data.get("installation_test"):
        return True
    store = token_store(hass, entry.data["token_store"])
    saved = await store.async_load()
    if not saved or not isinstance(saved.get("refresh_token"), str):
        raise ConfigEntryAuthFailed("Sign in to Blossom again")

    async def persist(refresh_token):
        await save_refresh_token(hass, entry.data["token_store"], refresh_token)

    client = BlossomClient(async_get_clientsession(hass), Tokens(saved["refresh_token"]), persist)
    coordinator = BlossomCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    live_card_label = coordinator.data.get("selected_card_label")
    if live_card_label and live_card_label != entry.data.get("card_label"):
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, "card_label": live_card_label}
        )
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if entry.data.get("installation_test"):
        return True
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    if key := entry.data.get("token_store"):
        await token_store(hass, key).async_remove()
