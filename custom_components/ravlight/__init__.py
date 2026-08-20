"""RavLight integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RavLightApiClient, RavLightApiError
from .const import CONF_HOST, CONF_PORT, DOMAIN, PLATFORMS
from .coordinator import RavLightDataUpdateCoordinator

type RavLightConfigEntry = ConfigEntry[RavLightDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RavLightConfigEntry) -> bool:
    """Set up RavLight from a config entry."""
    client = RavLightApiClient(
        async_get_clientsession(hass),
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
    )
    coordinator = RavLightDataUpdateCoordinator(hass, client)

    try:
        await coordinator.async_config_entry_first_refresh()
    except RavLightApiError as err:
        raise ConfigEntryNotReady(f"Unable to connect to RavLight device: {err}") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RavLightConfigEntry) -> bool:
    """Unload a RavLight config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
