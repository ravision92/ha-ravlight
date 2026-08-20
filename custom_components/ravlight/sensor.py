"""Sensors for RavLight."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorEntityDescription, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature

from .coordinator import RavLightCoordinatorEntity


@dataclass(frozen=True, kw_only=True)
class RavLightSensorDescription(SensorEntityDescription):
    """Describe a RavLight sensor."""

    source: str = "status"


SENSORS = (
    RavLightSensorDescription(key="temperature", translation_key="temperature", device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS, source="status"),
    RavLightSensorDescription(key="uptime", translation_key="uptime", entity_category=EntityCategory.DIAGNOSTIC, native_unit_of_measurement="s"),
    RavLightSensorDescription(key="total_hours", translation_key="total_hours", entity_category=EntityCategory.DIAGNOSTIC, native_unit_of_measurement="h", state_class=SensorStateClass.TOTAL_INCREASING),
    RavLightSensorDescription(key="motor_state", translation_key="motor_state", entity_category=EntityCategory.DIAGNOSTIC, source="motor"),
    RavLightSensorDescription(key="position_cm", translation_key="position_cm", native_unit_of_measurement="cm", source="motor"),
    RavLightSensorDescription(key="driver_temperature", translation_key="driver_temperature", device_class=SensorDeviceClass.TEMPERATURE, native_unit_of_measurement=UnitOfTemperature.CELSIUS, entity_category=EntityCategory.DIAGNOSTIC, source="motor"),
    RavLightSensorDescription(key="fault_flags", translation_key="fault_flags", entity_category=EntityCategory.DIAGNOSTIC, source="motor"),
)

_API_KEYS = {"driver_temperature": "driverTemp"}


class RavLightSensor(RavLightCoordinatorEntity, SensorEntity):
    """Representation of a RavLight status value."""

    entity_description: RavLightSensorDescription

    def __init__(self, coordinator, description: RavLightSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"

    @property
    def available(self) -> bool:
        return super().available and (
            self.entity_description.source == "status" or self.coordinator.data.get("motor") is not None
        )

    @property
    def native_value(self) -> Any:
        source = self.coordinator.data.get(self.entity_description.source) or {}
        return source.get(_API_KEYS.get(self.entity_description.key, self.entity_description.key))


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up RavLight sensors."""
    async_add_entities(RavLightSensor(entry.runtime_data, description) for description in SENSORS)
