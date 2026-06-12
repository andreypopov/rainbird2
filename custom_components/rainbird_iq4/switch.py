"""Switch entities for Rain Bird IQ4 stations."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_DEFAULT_DURATION, DATA_COORDINATOR, DEFAULT_DURATION_MINUTES, DOMAIN
from .coordinator import RainBirdIQ4Coordinator
from .entity import RainBirdIQ4Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdIQ4Coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        RainBirdIQ4StationSwitch(coordinator, entry, int(station["id"]))
        for station in coordinator.data.stations
        if station.get("id") is not None and station.get("satelliteId") is not None
    )


class RainBirdIQ4StationSwitch(RainBirdIQ4Entity, SwitchEntity):
    """Switch that starts and stops a station."""

    def __init__(
        self,
        coordinator: RainBirdIQ4Coordinator,
        entry: ConfigEntry,
        station_id: int,
    ) -> None:
        station = coordinator.data.stations_by_id[station_id]
        super().__init__(coordinator, int(station["satelliteId"]))
        self._entry = entry
        self.station_id = station_id
        self._attr_unique_id = f"rainbird_iq4_station_{station_id}"

    @property
    def station(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.stations_by_id.get(self.station_id, {})

    @property
    def name(self) -> str:
        station = self.station
        return station.get("name") or f"Station {self.station_id}"

    @property
    def is_on(self) -> bool:
        return self.coordinator.is_station_running(self.station_id)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        station = self.station
        attrs = {
            "station_id": self.station_id,
            "controller_id": self.controller_id,
            "terminal": station.get("terminal"),
            "landscape_type": station.get("areaLevel2Name"),
            "sprinkler_type": station.get("areaLevel3Name"),
            "remaining_seconds": self.coordinator.station_remaining_seconds(self.station_id),
        }
        return {key: value for key, value in attrs.items() if value is not None}

    async def async_turn_on(self, **kwargs: Any) -> None:
        duration = int(self._entry.options.get(CONF_DEFAULT_DURATION, DEFAULT_DURATION_MINUTES))
        await self.coordinator.async_start_stations([self.station_id], duration)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_stop_stations([self.station_id])

