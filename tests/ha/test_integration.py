"""Actual HA config-flow, entity, reload and removal tests with mocked cloud IO."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.blossom_energy.api import AuthError, ConnectionError

DOMAIN = "blossom_energy"


async def configure(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["step_id"] == "user"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "synthetic@example.invalid", "password": "synthetic-password"}
    )
    assert result["step_id"] == "scope"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"member_id": "member", "installation_id": "installation"}
    )
    assert result["step_id"] == "card"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"card_id": "card"})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return result["result"]


async def test_full_setup_entities_reload_and_delete(hass, mock_api):
    entry = await configure(hass)
    assert entry.state == ConfigEntryState.LOADED
    assert entry.unique_id == "synthetic-account"
    assert "password" not in entry.data and "refresh_token" not in entry.data
    saved = await Store(hass, 1, entry.data["token_store"]).async_load()
    assert saved == {"refresh_token": "synthetic-refresh"}
    states = hass.states.async_all("sensor")
    assert len(states) == 15
    assert any(s.state == "7.5" for s in states)
    assert "synthetic-refresh" not in str(states)
    assert "synthetic-password" not in str(states)
    assert len(hass.states.async_all("button")) == 3
    assert not hass.services.has_service(DOMAIN, "start_charging")
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state == ConfigEntryState.LOADED
    assert len(hass.states.async_all("sensor")) == 15
    key = entry.data["token_store"]
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert await Store(hass, 1, key).async_load() is None


async def test_start_and_stop_home_charging_buttons(hass, mock_api):
    entry = await configure(hass)
    registry = er.async_get(hass)
    start_id = registry.async_get_entity_id("button", DOMAIN, f"{entry.unique_id}_start_charging")
    stop_id = registry.async_get_entity_id("button", DOMAIN, f"{entry.unique_id}_stop_charging")
    assert start_id and stop_id
    assert hass.states.get(start_id).state != "unavailable"
    assert hass.states.get(stop_id).state == "unavailable"

    await hass.services.async_call("button", "press", {"entity_id": start_id}, blocking=True)
    mock_api["start"].assert_awaited_once_with(entry.runtime_data.scope, "card")

    mock_api["active"].return_value = [{"id": "active-session"}]
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(start_id).state == "unavailable"
    assert hass.states.get(stop_id).state != "unavailable"

    await hass.services.async_call("button", "press", {"entity_id": stop_id}, blocking=True)
    mock_api["stop"].assert_awaited_once_with(entry.runtime_data.scope)


async def test_login_failure_and_retry(hass, mock_api):
    mock_api["login"].side_effect = AuthError("authentication_failed")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "synthetic@example.invalid", "password": "synthetic-password"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert "synthetic-password" not in str(result)


async def test_duplicate_account_is_rejected(hass, mock_api):
    await configure(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "synthetic@example.invalid", "password": "synthetic-password"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_empty_history_is_valid(hass, mock_api):
    mock_api["sessions"].return_value = []
    entry = await configure(hass)
    assert entry.runtime_data.data["sessions"] == []
    assert entry.runtime_data.data["last_session"] == {}


async def test_failed_poll_marks_entities_unavailable(hass, mock_api):
    entry = await configure(hass)
    mock_api["current"].side_effect = ConnectionError("api_connection_failed")
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert not entry.runtime_data.last_update_success
    assert all(s.state == "unavailable" for s in hass.states.async_all("sensor"))


async def test_reauth_preserves_selection(hass, mock_api):
    entry = await configure(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}, data=entry.data
    )
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "synthetic@example.invalid", "password": "synthetic-password"}
    )
    assert result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.data["card_id"] == "card"
    assert entry.state == ConfigEntryState.LOADED


async def test_reauth_rejects_different_account(hass, mock_api):
    entry = await configure(hass)
    mock_api["current"].return_value = {"id": "other"}
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "reauth", "entry_id": entry.entry_id}, data=entry.data
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"email": "other@example.invalid", "password": "synthetic-password"}
    )
    assert result["reason"] == "wrong_account"


async def test_installation_test_entry_still_loads(hass):
    entry = MockConfigEntry(domain=DOMAIN, data={"installation_test": True})
    entry.add_to_hass(hass)
    with patch("custom_components.blossom_energy.BlossomClient") as client:
        assert await hass.config_entries.async_setup(entry.entry_id)
        assert await hass.config_entries.async_unload(entry.entry_id)
        client.assert_not_called()


async def test_silent_storage_failure_is_detected(hass):
    from custom_components.blossom_energy.storage import save_refresh_token

    with patch("homeassistant.helpers.storage.Store.async_save", new_callable=AsyncMock):
        with pytest.raises(OSError, match="token_storage_failed"):
            await save_refresh_token(hass, "blossom_energy.synthetic", "synthetic-refresh")
