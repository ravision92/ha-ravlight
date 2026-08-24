"""Firmware update status for RavLight.

Report-only. The device checks a manifest and says what the latest build for
its own board is, but flashing it means uploading the image to the device, so
installing from here is not offered — the "Check for update" button refreshes
the check and the web UI (or Polaris) does the flashing.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature

from .coordinator import RavLightCoordinatorEntity, RavLightDataUpdateCoordinator

# Home Assistant truncates the summary itself, but the release notes from the
# manifest can be long enough to be worth trimming with an ellipsis.
_SUMMARY_LIMIT = 250


class RavLightUpdateEntity(RavLightCoordinatorEntity, UpdateEntity):
    """The firmware state of one RavLight device."""

    _attr_supported_features = UpdateEntityFeature(0)
    _attr_translation_key = "firmware"

    def __init__(self, coordinator: RavLightDataUpdateCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._identity}_firmware"

    @property
    def _ota(self) -> dict[str, Any]:
        return self.coordinator.data.get("ota") or {}

    @property
    def installed_version(self) -> str | None:
        """Return the firmware currently running."""
        status = self.coordinator.data.get("status") or {}
        return self._ota.get("current") or status.get("fw")

    @property
    def latest_version(self) -> str | None:
        """Return the newest firmware the device knows about.

        Reported only when the device itself says an update is available. Home
        Assistant decides "update available" by comparing these two strings,
        while the firmware compares versions properly — and a manifest that
        lags behind a hand-flashed build really does name an older version
        than the one running, which would otherwise be offered as an update.

        Before any check has happened the honest answer is "the one running":
        reporting nothing would show as unknown, and an empty string would
        read as a downgrade.
        """
        if not self._ota.get("available"):
            return self.installed_version
        return self._ota.get("latest") or self.installed_version

    @property
    def release_summary(self) -> str | None:
        """Return the release notes of the available firmware."""
        notes = self._ota.get("notes")
        if not notes or not self._ota.get("available"):
            return None
        text = str(notes)
        return text if len(text) <= _SUMMARY_LIMIT else f"{text[:_SUMMARY_LIMIT]}…"


async def async_setup_entry(hass, entry, async_add_entities) -> None:
    """Set up the firmware update entity."""
    async_add_entities([RavLightUpdateEntity(entry.runtime_data)])
