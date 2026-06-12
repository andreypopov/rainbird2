"""Number entities for Rain Bird IQ4."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DATA_COORDINATOR, DOMAIN
from .coordinator import RainBirdIQ4Coordinator
from .entity import RainBirdIQ4Entity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: RainBirdIQ4Coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
    async_add_entities(
        RainBirdIQ4RainDelayNumber(coordinator, int(controller["id"]))
        for controller in coordinator.data.controllers
        if controller.get("id") is not None
    )


class RainBirdIQ4RainDelayNumber(RainBirdIQ4Entity, NumberEntity):
    """Rain delay number for a controller."""

    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_name = "Rain delay"
    _attr_native_max_value = 14
    _attr_native_min_value = 0
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.DAYS

    def __init__(self, coordinator: RainBirdIQ4Coordinator, controller_id: int) -> None:
        super().__init__(coordinator, controller_id)
        self._attr_unique_id = f"rainbird_iq4_controller_{controller_id}_rain_delay"

    @property
    def native_value(self) -> int | None:
        controller = self.controller
        value = controller.get("rainDelay", controller.get("rainDelayDaysRemaining"))
        return int(value) if value is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {"controller_id": self.controller_id}

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_rain_delay(self.controller_id, int(value))
