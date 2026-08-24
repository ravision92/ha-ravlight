"""Sensors for RavLight."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfLength,
    UnitOfTemperature,
    UnitOfTime,
)

from .const import (
    CONNECTION_MODE_SLUGS,
    DMX_SOURCE_SLUGS,
    FIXTURE_ORION,
    FIXTURE_VEYRON,
    LED_PROTOCOL_NAMES,
)
from .coordinator import RavLightCoordinatorEntity, RavLightDataUpdateCoordinator

CONNECTION_MODES = list(CONNECTION_MODE_SLUGS.values())


def _status(coordinator: RavLightDataUpdateCoordinator) -> dict[str, Any]:
    return coordinator.data.get("status") or {}


def _motor(coordinator: RavLightDataUpdateCoordinator) -> dict[str, Any]:
    return coordinator.data.get("motor") or {}


def _dmx_section(coordinator: RavLightDataUpdateCoordinator) -> dict[str, Any]:
    section = coordinator.config.get("dmx")
    return section if isinstance(section, dict) else {}


def _personality_name(coordinator: RavLightDataUpdateCoordinator) -> str | None:
    """Return the name of the personality the fixture is patched to."""
    try:
        active = int(coordinator.fixture_config.get("personality", 0))
    except (TypeError, ValueError):
        return None
    for personality in coordinator.personalities:
        if personality.get("idx") == active:
            return str(personality.get("name"))
    return str(active) if active else None


def _output_summary(coordinator: RavLightDataUpdateCoordinator) -> dict[str, Any]:
    """Return a per-output description, for the attributes of one sensor."""
    summary: dict[str, Any] = {}
    for index, output in enumerate(coordinator.outputs, start=1):
        pixels = int(output.get("count", 0) or 0)
        if pixels <= 0:
            continue
        protocol = LED_PROTOCOL_NAMES.get(
            int(output.get("proto", 0) or 0), "unknown"
        )
        summary[f"output_{index}"] = (
            f"{protocol}, {pixels} px, universe {output.get('univ', '?')}, "
            f"channel {output.get('ch', '?')}"
        )
    return summary


@dataclass(frozen=True, kw_only=True)
class RavLightSensorDescription(SensorEntityDescription):
    """Describe a RavLight sensor."""

    value_fn: Callable[[RavLightDataUpdateCoordinator], Any]
    exists_fn: Callable[[RavLightDataUpdateCoordinator], bool] = lambda _: True
    attrs_fn: Callable[[RavLightDataUpdateCoordinator], dict[str, Any]] | None = None
    needs_motor: bool = False


SENSORS: tuple[RavLightSensorDescription, ...] = (
    # ── Every fixture ───────────────────────────────────────────────────────
    RavLightSensorDescription(
        key="temperature",
        translation_key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        # Boards without the temperature module leave the key out entirely.
        exists_fn=lambda c: "temp" in _status(c),
        value_fn=lambda c: _status(c).get("temp"),
    ),
    RavLightSensorDescription(
        key="signal_strength",
        translation_key="signal_strength",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement="dBm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Meaningless on a wired link, where the firmware reports 0.
        exists_fn=lambda c: not c.features.get("ethernet")
        or _status(c).get("mode") == "WiFi",
        value_fn=lambda c: _status(c).get("rssi") or None,
    ),
    RavLightSensorDescription(
        key="connection",
        translation_key="connection",
        device_class=SensorDeviceClass.ENUM,
        options=CONNECTION_MODES,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: CONNECTION_MODE_SLUGS.get(_status(c).get("mode")),
    ),
    RavLightSensorDescription(
        key="ip_address",
        translation_key="ip_address",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _status(c).get("ip"),
    ),
    RavLightSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _status(c).get("uptime_sec"),
    ),
    RavLightSensorDescription(
        key="total_hours",
        translation_key="total_hours",
        native_unit_of_measurement=UnitOfTime.HOURS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda c: _status(c).get("total_hours"),
    ),
    RavLightSensorDescription(
        key="dmx_frame_rate",
        translation_key="dmx_frame_rate",
        native_unit_of_measurement="fps",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda c: _status(c).get("fps"),
    ),
    RavLightSensorDescription(
        key="dmx_source",
        translation_key="dmx_source",
        device_class=SensorDeviceClass.ENUM,
        options=list(DMX_SOURCE_SLUGS.values()),
        value_fn=lambda c: DMX_SOURCE_SLUGS.get(_dmx_section(c).get("input")),
    ),
    RavLightSensorDescription(
        key="universe",
        translation_key="universe",
        value_fn=lambda c: _dmx_section(c).get("universe"),
    ),
    RavLightSensorDescription(
        key="free_heap",
        translation_key="free_heap",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: _status(c).get("heap_free"),
    ),
    RavLightSensorDescription(
        key="minimum_heap",
        translation_key="minimum_heap",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.KIBIBYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda c: _status(c).get("heap_min"),
    ),
    RavLightSensorDescription(
        key="config_revision",
        translation_key="config_revision",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        # Firmware older than 2.23.15 does not report it.
        exists_fn=lambda c: "cfg_rev" in _status(c),
        value_fn=lambda c: _status(c).get("cfg_rev"),
    ),
    # ── Veyron ──────────────────────────────────────────────────────────────
    RavLightSensorDescription(
        key="personality",
        translation_key="personality",
        exists_fn=lambda c: c.fixture == FIXTURE_VEYRON,
        value_fn=_personality_name,
        attrs_fn=lambda c: {
            "footprint": next(
                (
                    p.get("footprint")
                    for p in c.personalities
                    if p.get("idx") == c.fixture_config.get("personality")
                ),
                None,
            )
        },
    ),
    RavLightSensorDescription(
        key="dmx_address",
        translation_key="dmx_address",
        exists_fn=lambda c: c.fixture == FIXTURE_VEYRON,
        value_fn=lambda c: c.fixture_config.get("rgbw"),
        attrs_fn=lambda c: {
            "accent_start": c.fixture_config.get("white"),
            "function_start": c.fixture_config.get("function"),
        },
    ),
    # ── Any fixture with LED outputs (Elyon, Axon, Orion with LEDs) ──────────
    RavLightSensorDescription(
        key="active_outputs",
        translation_key="active_outputs",
        exists_fn=lambda c: c.led_output_count > 0,
        value_fn=lambda c: len(c.active_outputs),
        attrs_fn=lambda c: {"hardware_outputs": c.led_output_count} | _output_summary(c),
    ),
    RavLightSensorDescription(
        key="total_pixels",
        translation_key="total_pixels",
        exists_fn=lambda c: c.led_output_count > 0,
        value_fn=lambda c: sum(
            int(output.get("count", 0) or 0) for output in c.active_outputs
        ),
    ),
    # ── Orion ───────────────────────────────────────────────────────────────
    RavLightSensorDescription(
        key="motor_state",
        translation_key="motor_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: _motor(c).get("state"),
    ),
    RavLightSensorDescription(
        key="position",
        translation_key="position",
        native_unit_of_measurement=UnitOfLength.CENTIMETERS,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: _motor(c).get("positionCm"),
        attrs_fn=lambda c: {
            "down_limit_cm": _motor(c).get("downCm"),
            "up_limit_cm": _motor(c).get("upCm"),
        },
    ),
    RavLightSensorDescription(
        key="driver_temperature",
        translation_key="driver_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        # The driver reports 0 when it has no reading to give.
        value_fn=lambda c: _motor(c).get("driverTemp") or None,
    ),
    RavLightSensorDescription(
        key="fault_flags",
        translation_key="fault_flags",
        entity_category=EntityCategory.DIAGNOSTIC,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: _motor(c).get("faultFlags"),
    ),
    RavLightSensorDescription(
        key="stallguard_result",
        translation_key="stallguard_result",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        value_fn=lambda c: _motor(c).get("sgResult"),
    ),
)


class RavLightSensor(RavLightCoordinatorEntity, SensorEntity):
    """A value read from a RavLight device."""

    entity_description: RavLightSensorDescription

    def __init__(
        self,
        coordinator: RavLightDataUpdateCoordinator,
        description: RavLightSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._identity}_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether the value behind this sensor is being reported."""
        if not super().available:
            return False
        if self.entity_description.needs_motor:
            motor = self.coordinator.data.get("motor")
            return bool(motor and motor.get("available", True))
        return True

    @property
    def native_value(self) -> Any:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the detail that belongs with this value."""
        if self.entity_description.attrs_fn is None:
            return None
        attributes = self.entity_description.attrs_fn(self.coordinator)
        return {key: value for key, value in attributes.items() if value is not None}


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the sensors this particular device actually has."""
    coordinator = entry.runtime_data
    async_add_entities(
        RavLightSensor(coordinator, description)
        for description in SENSORS
        if description.exists_fn(coordinator)
    )
