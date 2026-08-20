"""Buttons for safe, documented RavLight actions."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.exceptions import HomeAssistantError

from .coordinator import RavLightCoordinatorEntity

BUTTONS = (
    ButtonEntityDescription(key="highlight", translation_key="highlight", icon="mdi:lightbulb-auto-outline"),
    ButtonEntityDescription(key="release_dmx", translation_key="release_dmx", icon="mdi:remote"),
    ButtonEntityDescription(key="clear_fault", translation_key="clear_fault", icon="mdi:alert-remove"),
    ButtonEntityDescription(key="stop", translation_key="stop", icon="mdi:stop-circle-outline"),
)


class RavLightButton(RavLightCoordinatorEntity, ButtonEntity):
    """A safe command button for a RavLight device."""

    _attr_has_entity_name = True
    entity_description: ButtonEntityDescription

    def __init__(self, coordinator, description: ButtonEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.device_id}_{description.key}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC if description.key == "highlight" else None

    @property
    def available(self) -> bool:
        if self.entity_description.key in {"release_dmx", "clear_fault", "stop"}:
            return super().available and self.coordinator.data.get("motor") is not None
        return super().available

    async def async_press(self) -> None:
        """Execute the button action."""
        paths = {
            "highlight": "/highlight",
            "release_dmx": "/release-dmx",
            "clear_fault": "/clearfault",
            "stop": "/estop",
        }
        try:
            await self.coordinator.client.async_post(paths[self.entity_description.key])
        except Exception as err:
            raise HomeAssistantError(f"RavLight action failed: {err}") from err
        await self.coordinator.async_request_refresh()


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up RavLight buttons."""
    async_add_entities(RavLightButton(entry.runtime_data, description) for description in BUTTONS)
