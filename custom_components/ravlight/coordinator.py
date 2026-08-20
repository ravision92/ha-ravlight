"""Data coordinator for RavLight."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator, UpdateFailed

from .api import RavLightApiClient, RavLightApiError, RavLightConnectionError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS


class RavLightDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and coordinate RavLight state."""

    def __init__(self, hass, client: RavLightApiClient) -> None:
        super().__init__(
            hass,
            logger=logging.getLogger(__name__),
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self.device_id = "unknown"

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.async_get_status()
            features = await self.client.async_get_features()
            motor = await self.client.async_get_motor_status() if features.get("fixture") == "Orion" else None
        except RavLightConnectionError as err:
            raise UpdateFailed(f"Error communicating with RavLight: {err}") from err
        except RavLightApiError as err:
            raise UpdateFailed(f"Invalid RavLight response: {err}") from err
        self.device_id = str(status.get("id", "unknown"))
        return {"status": status, "features": features, "motor": motor}


class RavLightCoordinatorEntity(CoordinatorEntity[RavLightDataUpdateCoordinator]):
    """Base entity that belongs to a RavLight device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RavLightDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        status = coordinator.data["status"]
        device_id = str(status.get("id", "unknown"))
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"RavLight {device_id}",
            manufacturer="RavLight",
            model=str(status.get("board", "RavLight device")),
            sw_version=str(status.get("fw", "unknown")),
            configuration_url=f"http://{status.get('ip')}" if status.get("ip") else None,
        )
