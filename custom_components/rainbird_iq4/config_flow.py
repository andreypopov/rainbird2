"""Config flow for Rain Bird IQ4."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DEFAULT_DURATION,
    CONF_SCAN_INTERVAL,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
)
from .iq4_client import IQ4AuthError, IQ4CannotConnectError, IQ4Client, IQ4Error, IQ4WafChallengeError


async def _validate_input(hass: HomeAssistant, username: str, password: str) -> None:
    session = async_get_clientsession(hass)
    client = IQ4Client(session, username, password)
    await client.async_validate()


class RainBirdIQ4ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Rain Bird IQ4."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> RainBirdIQ4OptionsFlow:
        return RainBirdIQ4OptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await _validate_input(self.hass, username, password)
            except IQ4WafChallengeError:
                errors["base"] = "waf_challenge"
            except IQ4AuthError:
                errors["base"] = "invalid_auth"
            except IQ4CannotConnectError:
                errors["base"] = "cannot_connect"
            except IQ4Error:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(username.lower())
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_NAME: user_input[CONF_NAME],
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                    options={
                        CONF_DEFAULT_DURATION: DEFAULT_DURATION_MINUTES,
                        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MINUTES,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
                    vol.Required(CONF_USERNAME): cv.string,
                    vol.Required(CONF_PASSWORD): cv.string,
                }
            ),
            errors=errors,
        )


class RainBirdIQ4OptionsFlow(config_entries.OptionsFlow):
    """Handle options for Rain Bird IQ4."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DEFAULT_DURATION,
                        default=options.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=1, max=720)),
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES),
                    ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL_MINUTES, max=60)),
                }
            ),
        )

