"""Data coordinator for RavLight."""

from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import (
    RavLightApiClient,
    RavLightApiError,
    RavLightConnectionError,
    RavLightNotFoundError,
)
from .const import (
    DOMAIN,
    FIXTURE_ORION,
    LED_PROTOCOL_CLOCK_FOLLOWER,
    MANUFACTURER,
    OTA_INTERVAL_SECONDS,
    UPDATE_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)


class RavLightDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and coordinate the state of one RavLight device."""

    def __init__(self, hass: HomeAssistant, client: RavLightApiClient) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self.features: dict[str, Any] = {}
        self.personalities: list[dict[str, Any]] = []
        self.mac = ""
        self.device_id = "unknown"
        self._config: dict[str, Any] | None = None
        self._config_identity: tuple[Any, Any] | None = None
        self._ota: dict[str, Any] | None = None
        self._ota_fetched = 0.0

    async def _async_setup(self) -> None:
        """Read everything that is fixed for the life of the firmware image."""
        try:
            self.features = await self.client.async_get_features()
        except RavLightApiError as err:
            raise UpdateFailed(f"Cannot read device features: {err}") from err
        # Fixtures addressed per LED output (Elyon, Axon) legitimately return an
        # empty catalog, and firmware older than 2.23.15 has no route at all.
        try:
            catalog = await self.client.async_get_personalities()
        except RavLightApiError:
            self.personalities = []
        else:
            entries = catalog.get("personalities")
            self.personalities = entries if isinstance(entries, list) else []

    @property
    def fixture(self) -> str:
        """Return the fixture family of this device."""
        return str(self.features.get("fixture", ""))

    @property
    def led_output_count(self) -> int:
        """Return how many LED outputs the board physically has."""
        try:
            return int(self.features.get("hw_outputs", 0))
        except (TypeError, ValueError):
            return 0

    @property
    def config(self) -> dict[str, Any]:
        """Return the last device configuration read (without the password)."""
        return self._config or {}

    @property
    def fixture_config(self) -> dict[str, Any]:
        """Return the fixture section of the device configuration."""
        section = self.config.get("fixture")
        return section if isinstance(section, dict) else {}

    @property
    def outputs(self) -> list[dict[str, Any]]:
        """Return the configured LED outputs, if this fixture has any."""
        outputs = self.fixture_config.get("outputs")
        if not isinstance(outputs, list):
            return []
        return [output for output in outputs if isinstance(output, dict)]

    @property
    def active_outputs(self) -> list[dict[str, Any]]:
        """Return outputs that actually drive something.

        An output with no pixels is disabled, and a clock follower is the clock
        line of another output rather than an output of its own.
        """
        return [
            output
            for output in self.outputs
            if int(output.get("count", 0) or 0) > 0
            and int(output.get("proto", 0) or 0) != LED_PROTOCOL_CLOCK_FOLLOWER
        ]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            status = await self.client.async_get_status()
        except RavLightConnectionError as err:
            raise UpdateFailed(f"Error communicating with RavLight: {err}") from err
        except RavLightApiError as err:
            raise UpdateFailed(f"Invalid RavLight response: {err}") from err

        self.device_id = str(status.get("id", "unknown"))
        if mac := status.get("mac"):
            self.mac = format_mac(str(mac))

        await self._async_refresh_config_if_changed(status)

        motor: dict[str, Any] | None = None
        if self.fixture == FIXTURE_ORION:
            try:
                motor = await self.client.async_get_motor_status()
            except RavLightApiError as err:
                # A motor that stops answering must not take the whole device
                # offline: the network entities are still telling the truth.
                _LOGGER.debug("Motor status unavailable: %s", err)

        return {
            "status": status,
            "features": self.features,
            "config": self.config,
            "motor": motor,
            "ota": await self._async_refresh_ota(),
        }

    async def _async_refresh_config_if_changed(self, status: dict[str, Any]) -> None:
        """Re-read the configuration only when the device says it changed.

        cfg_rev and cfg_hash come free in every status reply, so a device that
        nobody is reconfiguring costs one request per cycle instead of two.
        Firmware older than 2.23.15 reports neither, which reads as (0, 0) and
        keeps the configuration cached after the first read.
        """
        identity = (status.get("cfg_rev"), status.get("cfg_hash"))
        if self._config is not None and identity == self._config_identity:
            return
        try:
            self._config = await self.client.async_get_config()
        except RavLightApiError as err:
            _LOGGER.debug("Configuration unavailable: %s", err)
            if self._config is None:
                self._config = {}
        self._config_identity = identity

    async def _async_refresh_ota(self) -> dict[str, Any] | None:
        """Return the device's update state, polled on its own slow interval."""
        now = time.monotonic()
        if self._ota is not None and now - self._ota_fetched < OTA_INTERVAL_SECONDS:
            return self._ota
        try:
            self._ota = await self.client.async_get_ota()
        except RavLightNotFoundError:
            self._ota = {}
        except RavLightApiError as err:
            _LOGGER.debug("Update state unavailable: %s", err)
            if self._ota is None:
                self._ota = {}
        self._ota_fetched = now
        return self._ota


class RavLightCoordinatorEntity(CoordinatorEntity[RavLightDataUpdateCoordinator]):
    """Base entity that belongs to a RavLight device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RavLightDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        status = coordinator.data["status"]
        # Keyed on the hardware MAC, never on the device id: the id is a label
        # the operator edits from the web UI, and a rename would orphan every
        # entity of the device.
        identifier = coordinator.mac or coordinator.device_id
        model = coordinator.fixture or "RavLight device"
        if board := status.get("board"):
            model = f"{model} ({board})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            connections=(
                {(CONNECTION_NETWORK_MAC, coordinator.mac)} if coordinator.mac else set()
            ),
            name=coordinator.device_id,
            manufacturer=MANUFACTURER,
            model=model,
            sw_version=str(status.get("fw", "unknown")),
            configuration_url=f"http://{coordinator.client.host}",
        )

    @property
    def _identity(self) -> str:
        """Return the stable per-device prefix for entity unique ids."""
        return self.coordinator.mac or self.coordinator.device_id
