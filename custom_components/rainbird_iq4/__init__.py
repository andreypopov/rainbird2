"""The Rain Bird IQ4 integration."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    ATTR_CONTROLLER_ID,
    ATTR_DAYS,
    ATTR_DURATION,
    ATTR_IS_GROUP_START,
    ATTR_STATION_ID,
    CONF_DEFAULT_DURATION,
    CONF_SCAN_INTERVAL,
    DATA_CLIENT,
    DATA_COORDINATOR,
    DEFAULT_DURATION_MINUTES,
    DEFAULT_SCAN_INTERVAL_MINUTES,
    DOMAIN,
    MIN_SCAN_INTERVAL_MINUTES,
    SERVICE_SET_RAIN_DELAY,
    SERVICE_START_STATION,
    SERVICE_STOP_ALL,
    SERVICE_STOP_STATION,
)
from .coordinator import RainBirdIQ4Coordinator
from .frontend import async_register_frontend
from .iq4_client import IQ4AuthError, IQ4Client, IQ4Error, IQ4WafChallengeError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.NUMBER, Platform.SWITCH]

STATION_IDS_SCHEMA = vol.Any(cv.positive_int, vol.All(cv.ensure_list, [cv.positive_int]))
CONTROLLER_IDS_SCHEMA = vol.Any(cv.positive_int, vol.All(cv.ensure_list, [cv.positive_int]))

START_STATION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_STATION_ID): STATION_IDS_SCHEMA,
        vol.Optional(ATTR_DURATION, default=DEFAULT_DURATION_MINUTES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=720)
        ),
        vol.Optional(ATTR_IS_GROUP_START, default=False): cv.boolean,
    }
)
STOP_STATION_SCHEMA = vol.Schema({vol.Required(ATTR_STATION_ID): STATION_IDS_SCHEMA})
STOP_ALL_SCHEMA = vol.Schema({vol.Required(ATTR_CONTROLLER_ID): CONTROLLER_IDS_SCHEMA})
SET_RAIN_DELAY_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CONTROLLER_ID): cv.positive_int,
        vol.Required(ATTR_DAYS): vol.All(vol.Coerce(int), vol.Range(min=0, max=14)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Rain Bird IQ4 from a config entry."""
    session = async_get_clientsession(hass)
    client = IQ4Client(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    interval_minutes = int(entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MINUTES))
    coordinator = RainBirdIQ4Coordinator(
        hass,
        client,
        timedelta(minutes=max(MIN_SCAN_INTERVAL_MINUTES, interval_minutes)),
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except IQ4WafChallengeError as err:
        raise ConfigEntryNotReady(str(err)) from err
    except IQ4AuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IQ4Error as err:
        raise ConfigEntryNotReady(str(err)) from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        DATA_CLIENT: client,
        DATA_COORDINATOR: coordinator,
    }

    await async_register_frontend(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_STATION):
        return

    async def async_start_station(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        station_ids = _as_int_list(call.data[ATTR_STATION_ID])
        await coordinator.async_start_stations(
            station_ids,
            int(call.data[ATTR_DURATION]),
            is_group_start=bool(call.data[ATTR_IS_GROUP_START]),
        )

    async def async_stop_station(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        await coordinator.async_stop_stations(_as_int_list(call.data[ATTR_STATION_ID]))

    async def async_stop_all(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        await coordinator.async_stop_all(_as_int_list(call.data[ATTR_CONTROLLER_ID]))

    async def async_set_rain_delay(call: ServiceCall) -> None:
        coordinator = _get_first_coordinator(hass)
        await coordinator.async_set_rain_delay(
            int(call.data[ATTR_CONTROLLER_ID]),
            int(call.data[ATTR_DAYS]),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_STATION,
        async_start_station,
        schema=START_STATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_STATION,
        async_stop_station,
        schema=STOP_STATION_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_ALL,
        async_stop_all,
        schema=STOP_ALL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_RAIN_DELAY,
        async_set_rain_delay,
        schema=SET_RAIN_DELAY_SCHEMA,
    )


def _get_first_coordinator(hass: HomeAssistant) -> RainBirdIQ4Coordinator:
    entries: dict[str, dict[str, Any]] = hass.data.get(DOMAIN, {})
    for entry_data in entries.values():
        if isinstance(entry_data, dict) and DATA_COORDINATOR in entry_data:
            return entry_data[DATA_COORDINATOR]
    raise HomeAssistantError("Rain Bird IQ4 is not configured")


def _as_int_list(value: Any) -> list[int]:
    if isinstance(value, list):
        return [int(item) for item in value]
    return [int(value)]
