"""Binary sensors for RavLight."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory

from .const import FIXTURE_ORION
from .coordinator import RavLightCoordinatorEntity, RavLightDataUpdateCoordinator


def _motor(coordinator: RavLightDataUpdateCoordinator) -> dict[str, Any]:
    return coordinator.data.get("motor") or {}


@dataclass(frozen=True, kw_only=True)
class RavLightBinarySensorDescription(BinarySensorEntityDescription):
    """Describe a RavLight binary sensor."""

    value_fn: Callable[[RavLightDataUpdateCoordinator], bool]
    exists_fn: Callable[[RavLightDataUpdateCoordinator], bool] = lambda _: True
    needs_motor: bool = False
    # Reachability has to keep reporting while the device is unreachable.
    survives_failure: bool = False


BINARY_SENSORS: tuple[RavLightBinarySensorDescription, ...] = (
    RavLightBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        entity_category=EntityCategory.DIAGNOSTIC,
        survives_failure=True,
        value_fn=lambda c: c.last_update_success,
    ),
    RavLightBinarySensorDescription(
        key="dmx_active",
        translation_key="dmx_active",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda c: bool((c.data.get("status") or {}).get("dmx_active")),
    ),
    RavLightBinarySensorDescription(
        key="homed",
        translation_key="homed",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: bool(_motor(c).get("homed")),
    ),
    RavLightBinarySensorDescription(
        key="motor_fault",
        translation_key="motor_fault",
        device_class=BinarySensorDeviceClass.PROBLEM,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: bool(_motor(c).get("faultFlags")),
    ),
    RavLightBinarySensorDescription(
        key="motor_busy",
        translation_key="motor_busy",
        device_class=BinarySensorDeviceClass.MOVING,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: bool(_motor(c).get("busy")),
    ),
    RavLightBinarySensorDescription(
        key="dmx_override",
        translation_key="dmx_override",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: bool(_motor(c).get("override")),
    ),
)


class RavLightBinarySensor(RavLightCoordinatorEntity, BinarySensorEntity):
    """A boolean state read from a RavLight device."""

    entity_description: RavLightBinarySensorDescription

    def __init__(
        self,
        coordinator: RavLightDataUpdateCoordinator,
        description: RavLightBinarySensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._identity}_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether this state is currently known."""
        if self.entity_description.survives_failure:
            return self.coordinator.data is not None
        if not super().available:
            return False
        if self.entity_description.needs_motor:
            motor = self.coordinator.data.get("motor")
            return bool(motor and motor.get("available", True))
        return True

    @property
    def is_on(self) -> bool:
        """Return the current state."""
        return self.entity_description.value_fn(self.coordinator)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the binary sensors this particular device actually has."""
    coordinator = entry.runtime_data
    async_add_entities(
        RavLightBinarySensor(coordinator, description)
        for description in BINARY_SENSORS
        if description.exists_fn(coordinator)
    )
