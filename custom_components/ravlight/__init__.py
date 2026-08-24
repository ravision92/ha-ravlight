"""RavLight integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RavLightApiClient, RavLightApiError
from .const import CONF_HOST, CONF_PORT, DEFAULT_PORT, DOMAIN, PLATFORMS
from .coordinator import RavLightDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

type RavLightConfigEntry = ConfigEntry[RavLightDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RavLightConfigEntry) -> bool:
    """Set up RavLight from a config entry."""
    client = RavLightApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
    )
    coordinator = RavLightDataUpdateCoordinator(hass, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except RavLightApiError as err:
        raise ConfigEntryNotReady(f"Unable to connect to RavLight device: {err}") from err

    # Must happen before the platforms are set up, so entities register under
    # the identity they will keep.
    await _async_migrate_to_mac_identity(hass, entry, coordinator)

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RavLightConfigEntry) -> bool:
    """Unload a RavLight config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_migrate_to_mac_identity(
    hass: HomeAssistant,
    entry: RavLightConfigEntry,
    coordinator: RavLightDataUpdateCoordinator,
) -> None:
    """Move a device that was keyed on its name over to its MAC.

    Entries created before identity moved to the hardware MAC used the device
    id — a label the operator can edit from the web UI, which meant renaming a
    fixture created a second device and orphaned every entity of the first.

    Deliberately done here rather than in async_migrate_entry: the MAC can only
    be learned from the device, so a migration that ran at load time would fail
    on any device that happened to be powered down. Here it simply happens the
    first time the device is reachable, and is a no-op afterwards.
    """
    mac = coordinator.mac
    legacy_id = entry.unique_id or coordinator.device_id
    if not mac or entry.unique_id == mac:
        return

    device_registry = dr.async_get(hass)
    if device := device_registry.async_get_device(identifiers={(DOMAIN, legacy_id)}):
        device_registry.async_update_device(
            device.id, new_identifiers={(DOMAIN, mac)}
        )

    @callback
    def _migrate_unique_id(registry_entry: er.RegistryEntry) -> dict[str, str] | None:
        prefix = f"{legacy_id}_"
        if registry_entry.unique_id.startswith(prefix):
            suffix = registry_entry.unique_id.removeprefix(prefix)
            return {"new_unique_id": f"{mac}_{suffix}"}
        return None

    await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

    try:
        hass.config_entries.async_update_entry(entry, unique_id=mac)
    except ValueError:
        # Another entry already holds this MAC — the same device was added
        # twice under two names. Leave both alone and let the user remove one.
        _LOGGER.warning(
            "RavLight device %s (%s) is already configured under another entry",
            coordinator.device_id,
            mac,
        )
        return

    _LOGGER.debug("Migrated RavLight %s from '%s' to %s", coordinator.device_id, legacy_id, mac)
