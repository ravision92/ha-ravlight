"""Buttons for RavLight actions.

Factory reset (POST /reset) is deliberately not exposed: it wipes the whole
configuration with no confirmation and no undo, which is not something a
dashboard button should be one tap away from.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .api import RavLightApiError
from .const import (
    FIXTURE_ELYON,
    FIXTURE_ORION,
    HIGHLIGHT_PATH,
    LED_HIGHLIGHT_PATH,
)
from .coordinator import RavLightCoordinatorEntity, RavLightDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class RavLightButtonDescription(ButtonEntityDescription):
    """Describe a RavLight action."""

    # Resolved per device: the same action lives on different routes depending
    # on the fixture.
    path_fn: Callable[[RavLightDataUpdateCoordinator], str]
    exists_fn: Callable[[RavLightDataUpdateCoordinator], bool] = lambda _: True
    needs_motor: bool = False


BUTTONS: tuple[RavLightButtonDescription, ...] = (
    RavLightButtonDescription(
        key="highlight",
        translation_key="highlight",
        icon="mdi:lightbulb-on-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        # Elyon is the exception: it has no /highlight route, only the LED one.
        path_fn=lambda c: LED_HIGHLIGHT_PATH
        if c.fixture == FIXTURE_ELYON
        else HIGHLIGHT_PATH,
    ),
    RavLightButtonDescription(
        key="led_highlight",
        translation_key="led_highlight",
        icon="mdi:led-strip-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        # Only where it is a second, distinct action: Axon and Orion have LED
        # outputs alongside their own highlight sequence.
        exists_fn=lambda c: c.led_output_count > 0 and c.fixture != FIXTURE_ELYON,
        path_fn=lambda _: LED_HIGHLIGHT_PATH,
    ),
    RavLightButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        path_fn=lambda _: "/restart",
    ),
    RavLightButtonDescription(
        key="check_update",
        translation_key="check_update",
        icon="mdi:cloud-search-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        path_fn=lambda _: "/api/ota/check",
    ),
    # ── Orion ───────────────────────────────────────────────────────────────
    RavLightButtonDescription(
        key="home",
        translation_key="home",
        icon="mdi:home-import-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path_fn=lambda _: "/home",
    ),
    RavLightButtonDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop-circle-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path_fn=lambda _: "/estop",
    ),
    RavLightButtonDescription(
        key="clear_fault",
        translation_key="clear_fault",
        icon="mdi:alert-remove-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path_fn=lambda _: "/clearfault",
    ),
    RavLightButtonDescription(
        key="release_dmx",
        translation_key="release_dmx",
        icon="mdi:remote",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path_fn=lambda _: "/release-dmx",
    ),
)


class RavLightButton(RavLightCoordinatorEntity, ButtonEntity):
    """An action on a RavLight device."""

    entity_description: RavLightButtonDescription

    def __init__(
        self,
        coordinator: RavLightDataUpdateCoordinator,
        description: RavLightButtonDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._identity}_{description.key}"

    @property
    def available(self) -> bool:
        """Return whether this action can be taken right now."""
        if not super().available:
            return False
        if self.entity_description.needs_motor:
            motor = self.coordinator.data.get("motor")
            return bool(motor and motor.get("available", True))
        return True

    async def async_press(self) -> None:
        """Run the action."""
        path = self.entity_description.path_fn(self.coordinator)
        try:
            await self.coordinator.client.async_post(path)
        except RavLightApiError as err:
            # The firmware refuses some actions in some states — homing in
            # manual mode, for instance — and says why in the response.
            raise HomeAssistantError(f"RavLight {path} failed: {err}") from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the actions this particular device actually supports."""
    coordinator = entry.runtime_data
    async_add_entities(
        RavLightButton(coordinator, description)
        for description in BUTTONS
        if description.exists_fn(coordinator)
    )
