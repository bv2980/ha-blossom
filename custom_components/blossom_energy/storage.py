"""Private atomic token storage with write verification."""

from homeassistant.helpers.storage import Store


def token_store(hass, key):
    """Use restrictive permissions and atomic replacement for refresh tokens."""
    return Store(hass, 1, key, private=True, atomic_writes=True)


async def save_refresh_token(hass, key, refresh_token):
    """Verify persistence because HA Store logs some write failures internally."""
    expected = {"refresh_token": refresh_token}
    try:
        await token_store(hass, key).async_save(expected)
        # A new store avoids interpreting a pending in-memory write as success.
        stored = await token_store(hass, key).async_load()
        if stored != expected:
            raise OSError("token_storage_failed")
    except Exception:
        raise OSError("token_storage_failed") from None
