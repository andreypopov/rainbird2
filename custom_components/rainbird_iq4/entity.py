"""Base entities for Rain Bird IQ4."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_NAME, CONNECTION_NETWORK_MAC
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import RainBirdIQ4Coordinator


class RainBirdIQ4Entity(CoordinatorEntity[RainBirdIQ4Coordinator]):
    """Base Rain Bird IQ4 entity."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RainBirdIQ4Coordinator, controller_id: int) -> None:
        super().__init__(coordinator)
        self.controller_id = controller_id

    @property
    def controller(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return self.coordinator.data.controllers_by_id.get(self.controller_id, {})

    @property
    def device_info(self) -> DeviceInfo:
        controller = self.controller
        device_info: DeviceInfo = {
            "identifiers": {(DOMAIN, f"controller_{self.controller_id}")},
            "manufacturer": MANUFACTURER,
            "name": controller.get("name") or controller.get(CONF_NAME) or f"Controller {self.controller_id}",
        }
        if version := controller.get("version"):
            device_info["sw_version"] = str(version)
        if model := controller.get("type"):
            device_info["model"] = str(model)
        if mac := controller.get("macAddress"):
            device_info["connections"] = {(CONNECTION_NETWORK_MAC, str(mac))}
        return device_info

    @property
    def available(self) -> bool:
        if not self.coordinator.data:
            return False
        return self.coordinator.data.connection_statuses.get(self.controller_id, True)

