"""Binary sensors for RavLight."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.entity import EntityCategory

from .coordinator import RavLightCoordinatorEntity


class RavLightOnlineBinarySensor(RavLightCoordinatorEntity, BinarySensorEntity):
    """Whether Home Assistant can currently reach the RavLight device."""

    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator) -> None:
        """Initialize the online sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.device_id}_online"

    @property
    def available(self) -> bool:
        """Keep the entity available so a failed update reports Off."""
        return self.coordinator.data is not None

    @property
    def is_on(self) -> bool:
        """Return whether the most recent coordinator update succeeded."""
        return self.coordinator.last_update_success


class RavLightDmxActiveBinarySensor(RavLightCoordinatorEntity, BinarySensorEntity):
    """Whether RavLight is receiving DMX traffic."""

    _attr_has_entity_name = True
    _attr_name = "DMX active"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data["status"].get("dmx_active"))


class RavLightHomedBinarySensor(RavLightCoordinatorEntity, BinarySensorEntity):
    """Whether the Orion fixture has a valid position reference."""

    _attr_has_entity_name = True
    _attr_name = "Homed"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("motor") is not None

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data.get("motor", {}).get("homed"))


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up RavLight binary sensors."""
    async_add_entities([
        RavLightOnlineBinarySensor(entry.runtime_data),
        RavLightDmxActiveBinarySensor(entry.runtime_data),
        RavLightHomedBinarySensor(entry.runtime_data),
    ])
