"""UI login, explicit scope selection and reauthentication."""

import secrets

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from homeassistant.helpers.storage import Store

from .api import (
    AuthError,
    BlossomClient,
    ConnectionError,
    PermissionError,
    ProtocolError,
    RateLimitError,
    login,
)
from .const import DOMAIN
from .models import scope_choices, session_summaries

API_ERRORS = (AuthError, ConnectionError, PermissionError, ProtocolError, RateLimitError)


def error_key(error):
    if isinstance(error, AuthError):
        return "invalid_auth"
    if isinstance(error, ConnectionError):
        return "cannot_connect"
    if isinstance(error, RateLimitError):
        return "rate_limited"
    if isinstance(error, PermissionError):
        return "scope_denied"
    return "unsupported_response"


class BlossomEnergyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """One explicitly selected installation per account."""

    VERSION = 1

    def __init__(self):
        self.client = None
        self.user = None
        self.members = {}
        self.installations = {}
        self.scope = {}
        self.cards = []
        self.reauth_entry = None

    async def async_step_reauth(self, entry_data):
        self.reauth_entry = self._get_reauth_entry()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._login_step("reauth_confirm", user_input)

    async def async_step_user(self, user_input=None):
        return await self._login_step("user", user_input)

    async def _login_step(self, step, user_input):
        errors = {}
        if user_input is not None:
            try:
                tokens = await login(user_input[CONF_EMAIL].strip(), user_input[CONF_PASSWORD])
                self.client = BlossomClient(async_get_clientsession(self.hass), tokens)
                self.user = await self.client.current_user()
                if self.reauth_entry:
                    if self.user["id"] != self.reauth_entry.data["account_id"]:
                        return self.async_abort(reason="wrong_account")
                else:
                    await self.async_set_unique_id(self.user["id"])
                    self._abort_if_unique_id_configured()
                self.members, self.installations = scope_choices(self.user)
                if self.reauth_entry:
                    self.scope = {
                        key: self.reauth_entry.data[key]
                        for key in ("member_id", "installation_id", "company_id")
                    }
                    member = self.members.get(self.scope["member_id"])
                    if (
                        not member
                        or member["companyId"] != self.scope["company_id"]
                        or self.scope["installation_id"] not in self.installations
                    ):
                        raise PermissionError("scope_changed")
                    await self.client.cards(self.scope)
                    await Store(self.hass, 1, self.reauth_entry.data["token_store"]).async_save(
                        {"refresh_token": self.client.tokens.refresh_token}
                    )
                    return self.async_update_reload_and_abort(self.reauth_entry, data_updates={})
                return await self.async_step_scope()
            except API_ERRORS as err:
                errors["base"] = error_key(err)
            except OSError:
                errors["base"] = "storage_failed"
            finally:
                user_input.pop(CONF_PASSWORD, None)
        return self.async_show_form(
            step_id=step,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_scope(self, user_input=None):
        errors = {}
        if user_input is not None:
            member_id, installation_id = user_input["member_id"], user_input["installation_id"]
            if member_id not in self.members or installation_id not in self.installations:
                errors["base"] = "scope_denied"
            else:
                self.scope = {
                    "member_id": member_id,
                    "installation_id": installation_id,
                    "company_id": self.members[member_id]["companyId"],
                }
                try:
                    self.cards = await self.client.cards(self.scope)
                    if not self.cards:
                        errors["base"] = "no_cards"
                    else:
                        return await self.async_step_card()
                except API_ERRORS as err:
                    errors["base"] = error_key(err)
        members = {
            key: f"{value.get('name') or value.get('email') or 'Member'} ({key})"
            for key, value in self.members.items()
        }
        installations = {
            key: f"{value.get('name') or value.get('label') or 'Installation'} ({key})"
            for key, value in self.installations.items()
        }
        return self.async_show_form(
            step_id="scope",
            data_schema=vol.Schema(
                {
                    vol.Required("member_id"): vol.In(members),
                    vol.Required("installation_id"): vol.In(installations),
                }
            ),
            errors=errors,
        )

    async def async_step_card(self, user_input=None):
        errors = {}
        choices = {
            card["id"]: f"{card.get('label') or 'Card'} ({card.get('type', 'unknown')})"
            for card in self.cards
        }
        if user_input is not None:
            card_id = user_input["card_id"]
            if card_id not in choices:
                errors["base"] = "scope_denied"
            else:
                key = f"{DOMAIN}.{secrets.token_hex(16)}"
                try:
                    session_summaries(await self.client.recent_sessions(self.scope))
                    await Store(self.hass, 1, key).async_save(
                        {"refresh_token": self.client.tokens.refresh_token}
                    )
                    return self.async_create_entry(
                        title="Blossom Energy",
                        data={
                            "account_id": self.user["id"],
                            **self.scope,
                            "card_id": card_id,
                            "card_label": choices[card_id],
                            "token_store": key,
                        },
                    )
                except API_ERRORS as err:
                    errors["base"] = error_key(err)
                except OSError:
                    errors["base"] = "storage_failed"
        return self.async_show_form(
            step_id="card",
            data_schema=vol.Schema(
                {
                    vol.Required("card_id"): vol.In(choices),
                }
            ),
            errors=errors,
        )
