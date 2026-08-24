"""Buttons for RavLight actions.

Factory reset (POST /reset) is deliberately not exposed: it wipes the whole
configuration with no confirmation and no undo, which is not something a
dashboard button should be one tap away from.
"""

from __future__ import annotations

import asyncio
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
from .coordinator import (
    RavLightCoordinatorEntity,
    RavLightDataUpdateCoordinator,
    output_is_active,
)

# Gap between per-output wipes when identifying a whole multi-output fixture.
# Long enough to read as separate outputs, short enough not to block the press.
_WIPE_GAP = 0.4


@dataclass(frozen=True, kw_only=True)
class RavLightButtonDescription(ButtonEntityDescription):
    """Describe a RavLight action."""

    path: str
    exists_fn: Callable[[RavLightDataUpdateCoordinator], bool] = lambda _: True
    needs_motor: bool = False


BUTTONS: tuple[RavLightButtonDescription, ...] = (
    RavLightButtonDescription(
        key="highlight",
        translation_key="highlight",
        icon="mdi:lightbulb-on-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        # Elyon has no /highlight route at all — identifying one is a wipe per
        # output, handled by RavLightIdentifyButton below.
        exists_fn=lambda c: c.fixture != FIXTURE_ELYON,
        path=HIGHLIGHT_PATH,
    ),
    RavLightButtonDescription(
        key="restart",
        translation_key="restart",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        path="/restart",
    ),
    RavLightButtonDescription(
        key="check_update",
        translation_key="check_update",
        icon="mdi:cloud-search-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        path="/api/ota/check",
    ),
    # ── Orion ───────────────────────────────────────────────────────────────
    RavLightButtonDescription(
        key="home",
        translation_key="home",
        icon="mdi:home-import-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path="/home",
    ),
    RavLightButtonDescription(
        key="stop",
        translation_key="stop",
        icon="mdi:stop-circle-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path="/estop",
    ),
    RavLightButtonDescription(
        key="clear_fault",
        translation_key="clear_fault",
        icon="mdi:alert-remove-outline",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path="/clearfault",
    ),
    RavLightButtonDescription(
        key="release_dmx",
        translation_key="release_dmx",
        icon="mdi:remote",
        exists_fn=lambda c: c.fixture == FIXTURE_ORION,
        needs_motor=True,
        path="/release-dmx",
    ),
)


class RavLightButtonBase(RavLightCoordinatorEntity, ButtonEntity):
    """Shared error handling for anything that pokes an action endpoint."""

    async def _async_call(self, path: str, data: dict[str, int] | None = None) -> None:
        try:
            await self.coordinator.client.async_post(path, data)
        except RavLightApiError as err:
            # The firmware refuses some actions in some states — homing while
            # in manual mode, for instance — and says why in the response.
            raise HomeAssistantError(f"RavLight {path} failed: {err}") from err


class RavLightButton(RavLightButtonBase):
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
        await self._async_call(self.entity_description.path)
        await self.coordinator.async_request_refresh()


class RavLightOutputIdentifyButton(RavLightButtonBase):
    """Wipe one LED output white, to find which physical run it drives.

    The firmware wants the output index in the POST body (`out=<i>`, 0-based,
    the same call the web UI's per-row identify makes), so this cannot be a
    single fixture-wide button.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "identify_output"
    _attr_icon = "mdi:led-strip-variant"

    def __init__(
        self, coordinator: RavLightDataUpdateCoordinator, index: int
    ) -> None:
        super().__init__(coordinator)
        self._index = index
        self._attr_unique_id = f"{self._identity}_identify_output_{index + 1}"
        self._attr_translation_placeholders = {"output": str(index + 1)}

    async def async_press(self) -> None:
        """Wipe this output."""
        await self._async_call(LED_HIGHLIGHT_PATH, {"out": self._index})


class RavLightElyonIdentifyButton(RavLightButtonBase):
    """Identify an Elyon by wiping each of its outputs in turn.

    Elyon serves no /highlight route — its fixtureHighlight() is a no-op — so
    the fixture-wide identify every other fixture has is built here out of the
    per-output wipes, rather than leaving one fixture without one.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "highlight"
    _attr_icon = "mdi:lightbulb-on-outline"

    def __init__(self, coordinator: RavLightDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._identity}_highlight"

    async def async_press(self) -> None:
        """Wipe every configured output, one after another."""
        for position, output in enumerate(self.coordinator.outputs):
            if not output_is_active(output):
                continue
            await self._async_call(LED_HIGHLIGHT_PATH, {"out": position})
            await asyncio.sleep(_WIPE_GAP)


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the actions this particular device actually supports."""
    coordinator = entry.runtime_data
    entities: list[ButtonEntity] = [
        RavLightButton(coordinator, description)
        for description in BUTTONS
        if description.exists_fn(coordinator)
    ]
    if coordinator.fixture == FIXTURE_ELYON and coordinator.active_outputs:
        entities.append(RavLightElyonIdentifyButton(coordinator))
    # One per output that drives something — an output with no pixels, or one
    # consumed as another's clock line, has nothing to wipe.
    entities.extend(
        RavLightOutputIdentifyButton(coordinator, index)
        for index, output in enumerate(coordinator.outputs)
        if output_is_active(output)
    )
    async_add_entities(entities)
