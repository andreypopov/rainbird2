"""Binary sensors for Rain Bird IQ4."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
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
        RainBirdIQ4ConnectionSensor(coordinator, int(controller["id"]))
        for controller in coordinator.data.controllers
        if controller.get("id") is not None
    )


class RainBirdIQ4ConnectionSensor(RainBirdIQ4Entity, BinarySensorEntity):
    """Controller cloud connection state."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_name = "Connection"

    def __init__(self, coordinator: RainBirdIQ4Coordinator, controller_id: int) -> None:
        super().__init__(coordinator, controller_id)
        self._attr_unique_id = f"rainbird_iq4_controller_{controller_id}_connection"

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.connection_statuses.get(self.controller_id)

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {"controller_id": self.controller_id}
