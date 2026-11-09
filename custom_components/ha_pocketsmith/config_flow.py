"""Config flow for PocketSmith."""
import asyncio
import json
import logging
from typing import Any, cast

import aiohttp
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import (
    CONF_ENABLE_BACKFILL,
    CONF_POCKETSMITH_USER_ID,
    DEFAULT_ENABLE_BACKFILL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
_API_ME = "https://api.pocketsmith.com/v2/me"
_TIMEOUT = 10


async def _validate_developer_key(hass: HomeAssistant, developer_key: str) -> int:
    """Validate a key and return the immutable PocketSmith user ID."""
    headers = {
        "Accept": "application/json",
        "Authorization": "Key %s" % developer_key,
    }
    session = async_get_clientsession(hass)
    async with asyncio.timeout(_TIMEOUT):
        async with session.get(_API_ME, headers=headers) as response:
            if response.status == 401:
                raise ValueError("invalid_auth")
            if response.status == 403:
                raise ValueError("insufficient_permissions")
            response.raise_for_status()
            try:
                profile = await response.json()
            except (aiohttp.ContentTypeError, json.JSONDecodeError) as err:
                raise ValueError("invalid_response") from err
            user_id = profile.get("id") if isinstance(profile, dict) else None
            if not isinstance(user_id, int) or isinstance(user_id, bool):
                raise ValueError("invalid_response")
            return user_id


def _known_user_id(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """Find the original identity, including for entries made before it was stored."""
    user_id = entry.data.get(CONF_POCKETSMITH_USER_ID)
    if user_id is not None:
        return str(user_id)
    registry = dr.async_get(hass)
    identifiers = {
        identifier
        for device in dr.async_entries_for_config_entry(registry, entry.entry_id)
        for domain, identifier in device.identifiers
        if domain == DOMAIN
    }
    return next(iter(identifiers)) if len(identifiers) == 1 else None


async def _validate_replacement_key(hass: HomeAssistant, entry: ConfigEntry, developer_key: str) -> int:
    """Refuse to attach an existing entry to another PocketSmith account."""
    user_id = await _validate_developer_key(hass, developer_key)
    original_user_id = _known_user_id(hass, entry)
    if original_user_id is None:
        raise ValueError("cannot_verify_account")
    if str(user_id) != original_user_id:
        raise ValueError("wrong_account")
    return user_id


class PocketSmithOptionsFlow(config_entries.OptionsFlow):
    """Handle PocketSmith options."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options form."""
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})

        current = self.config_entry.options
        schema = vol.Schema({
            vol.Required(
                CONF_ENABLE_BACKFILL,
                default=current.get(CONF_ENABLE_BACKFILL, DEFAULT_ENABLE_BACKFILL),
            ): bool,
        })

        return self.async_show_form(step_id="init", data_schema=cast(Any, schema))


class PocketSmithConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the PocketSmith UI setup flow."""

    VERSION = 2
    MINOR_VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: ConfigEntry) -> PocketSmithOptionsFlow:
        """Return the options flow handler."""
        return PocketSmithOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        errors = {}
        if user_input is not None:
            try:
                user_id = await _validate_developer_key(self.hass, user_input["developer_key"])
            except ValueError as err:
                errors["base"] = str(err)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except asyncio.TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during PocketSmith config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="PocketSmith",
                    data={"developer_key": user_input["developer_key"], CONF_POCKETSMITH_USER_ID: user_id},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=cast(Any, vol.Schema({vol.Required("developer_key"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle re-authentication when the developer key is rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle re-authentication confirmation."""
        errors = {}
        if user_input is not None:
            try:
                user_id = await _validate_replacement_key(self.hass, self._get_reauth_entry(), user_input["developer_key"])
            except ValueError as err:
                errors["base"] = str(err)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except asyncio.TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during PocketSmith reauth")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._get_reauth_entry(),
                    data={**self._get_reauth_entry().data, "developer_key": user_input["developer_key"], CONF_POCKETSMITH_USER_ID: user_id},
                )
                await self.hass.config_entries.async_reload(self._get_reauth_entry().entry_id)
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=cast(Any, vol.Schema({vol.Required("developer_key"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))})),
            errors=errors,
        )

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Allow the user to update their developer key from the 3-dot menu."""
        errors = {}
        if user_input is not None:
            try:
                user_id = await _validate_replacement_key(self.hass, self._get_reconfigure_entry(), user_input["developer_key"])
            except ValueError as err:
                errors["base"] = str(err)
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"
            except asyncio.TimeoutError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during PocketSmith reconfigure")
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self._get_reconfigure_entry(),
                    data={**self._get_reconfigure_entry().data, "developer_key": user_input["developer_key"], CONF_POCKETSMITH_USER_ID: user_id},
                )
                await self.hass.config_entries.async_reload(self._get_reconfigure_entry().entry_id)
                return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=cast(Any, vol.Schema({
                vol.Required("developer_key"): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
            })),
            errors=errors,
        )
