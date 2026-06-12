"""Data coordinator for Rain Bird IQ4."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .iq4_client import IQ4AuthError, IQ4Client, IQ4Error, IQ4WafChallengeError

_LOGGER = logging.getLogger(__name__)


@dataclass
class RainBirdIQ4Data:
    """Runtime data fetched from IQ4."""

    sites: list[dict[str, Any]]
    controllers: list[dict[str, Any]]
    stations: list[dict[str, Any]]
    connection_statuses: dict[int, bool]
    controllers_by_id: dict[int, dict[str, Any]]
    stations_by_id: dict[int, dict[str, Any]]


class RainBirdIQ4Coordinator(DataUpdateCoordinator[RainBirdIQ4Data]):
    """Coordinate IQ4 data updates and manual operations."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: IQ4Client,
        update_interval: timedelta,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )
        self.client = client
        self._running_until: dict[int, datetime] = {}

    async def _async_update_data(self) -> RainBirdIQ4Data:
        try:
            sites = await self.client.get_sites()
            controllers = await self.client.get_controllers()
            controller_ids = [
                int(controller["id"])
                for controller in controllers
                if controller.get("id") is not None
            ]
            connection_statuses = await self.client.get_connection_statuses(controller_ids)

            station_results = await asyncio.gather(
                *(self.client.get_stations(controller_id) for controller_id in controller_ids),
                return_exceptions=True,
            )
        except IQ4AuthError as err:
            raise ConfigEntryAuthFailed("Rain Bird IQ4 rejected the username or password") from err
        except IQ4WafChallengeError as err:
            raise UpdateFailed(
                "Rain Bird IQ4 login is protected by an AWS WAF browser challenge; "
                "Home Assistant will retry later"
            ) from err
        except IQ4Error as err:
            raise UpdateFailed(str(err)) from err

        stations: list[dict[str, Any]] = []
        for controller_id, result in zip(controller_ids, station_results, strict=False):
            if isinstance(result, Exception):
                _LOGGER.warning("Could not fetch stations for IQ4 controller %s: %s", controller_id, result)
                continue
            for station in result:
                station.setdefault("satelliteId", controller_id)
                stations.append(station)

        self._purge_finished_runs()
        controllers_by_id = {
            int(controller["id"]): controller
            for controller in controllers
            if controller.get("id") is not None
        }
        stations_by_id = {
            int(station["id"]): station
            for station in stations
            if station.get("id") is not None
        }
        return RainBirdIQ4Data(
            sites=sites,
            controllers=controllers,
            stations=stations,
            connection_statuses=connection_statuses,
            controllers_by_id=controllers_by_id,
            stations_by_id=stations_by_id,
        )

    async def async_start_stations(
        self,
        station_ids: list[int],
        duration_minutes: int,
        *,
        is_group_start: bool = False,
    ) -> None:
        seconds = max(1, int(duration_minutes)) * 60
        await self.client.start_stations(
            station_ids,
            [seconds] * len(station_ids),
            is_group_start=is_group_start,
        )
        until = dt_util.utcnow() + timedelta(seconds=seconds)
        for station_id in station_ids:
            self._running_until[int(station_id)] = until
        self.async_update_listeners()

    async def async_stop_stations(self, station_ids: list[int]) -> None:
        await self.client.stop_stations(station_ids)
        for station_id in station_ids:
            self._running_until.pop(int(station_id), None)
        self.async_update_listeners()

    async def async_stop_all(self, controller_ids: list[int]) -> None:
        await self.client.stop_all_irrigation(controller_ids)
        if self.data:
            affected_station_ids = {
                station_id
                for station_id, station in self.data.stations_by_id.items()
                if int(station.get("satelliteId", 0)) in controller_ids
            }
            for station_id in affected_station_ids:
                self._running_until.pop(station_id, None)
        self.async_update_listeners()

    async def async_set_rain_delay(self, controller_id: int, days: int) -> None:
        await self.client.set_rain_delay(controller_id, days)
        if self.data and (controller := self.data.controllers_by_id.get(controller_id)):
            controller["rainDelay"] = days
        self.async_update_listeners()

    def is_station_running(self, station_id: int) -> bool:
        self._purge_finished_runs()
        if station_id in self._running_until:
            return True
        if not self.data:
            return False
        station = self.data.stations_by_id.get(station_id)
        if not station:
            return False
        for key in ("runTimeRemaining", "runtimeRemaining", "secondsRemaining", "remainingSeconds"):
            value = station.get(key)
            if isinstance(value, (int, float)) and value > 0:
                return True
        status = str(
            station.get("irrigationStatus")
            or station.get("status")
            or station.get("state")
            or ""
        ).lower()
        return any(word in status for word in ("running", "started", "readytorun"))

    def station_remaining_seconds(self, station_id: int) -> int | None:
        self._purge_finished_runs()
        until = self._running_until.get(station_id)
        if not until:
            return None
        return max(0, int((until - dt_util.utcnow()).total_seconds()))

    def _purge_finished_runs(self) -> None:
        now = dt_util.utcnow()
        expired = [station_id for station_id, until in self._running_until.items() if until <= now]
        for station_id in expired:
            self._running_until.pop(station_id, None)
